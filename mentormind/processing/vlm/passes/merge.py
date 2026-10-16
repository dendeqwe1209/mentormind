"""Pass C — merge (spec 04 §3, T04-5).

A text LLM (no images) receives every kept step with an id, its segment index and times, and
returns merged steps, each naming the input ids (``source_ids``) it came from. It may merge one
action cut in two by a segment boundary, and rewrite names verb-first; it may NOT add a step.

Nothing the LLM says is trusted blindly (AC-05, "so khớp ngược"):

* a returned step without a known, unused source id is dropped — that is an invented step;
* a returned step whose text does not match any of its sources (``token_set_ratio >= 70``) is
  rejected: its sources are kept as they were;
* sources must lie in the same or adjacent segments and share one ``actor`` (a person and a robot
  never make one step), otherwise the merge is rejected likewise; the merged step's ``actor`` is
  its sources' — the LLM cannot change it;
* an input step the LLM left out is kept as it was.

The prompt goes through the LLM guard like any other call: its classification is the strictest of
the segments involved, so factory data never reaches a cloud LLM (constitution art. 2).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from itertools import pairwise
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from mentormind.core.providers.errors import InvalidJSONError
from mentormind.core.providers.llm import LLMProvider, strictest
from mentormind.core.providers.parsing import parse_json_object
from mentormind.core.schemas.video import Segment
from mentormind.processing.vlm.passes.matching import MATCH_THRESHOLD, similarity
from mentormind.processing.vlm.passes.models import PassAResult, TimedStep
from mentormind.processing.vlm.passes.prompting import render_prompt

log = logging.getLogger(__name__)

PASS_C_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "step": {"type": "string"},
                    "source_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["step", "source_ids"],
            },
        }
    },
    "required": ["steps"],
}


class MergedStep(BaseModel):
    model_config = ConfigDict(extra="ignore")

    step: str = Field(min_length=3)
    source_ids: list[str] = Field(default_factory=list)


class PassCOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    steps: list[MergedStep]


class MergeReport(BaseModel):
    """What pass C did — kept next to the raw answer for debugging (FR-06)."""

    merged: int = 0
    renamed: int = 0
    invented_dropped: int = 0
    rejected: int = 0
    kept_unchanged: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str | None = None


def merge_steps(
    result: PassAResult,
    segments: Sequence[Segment],
    llm: LLMProvider,
    *,
    process_id: str,
    work_dir: Path,
    threshold: float = MATCH_THRESHOLD,
) -> tuple[PassAResult, MergeReport]:
    """Pass C over ``result.steps``; the LLM answer is checked against the input (AC-05)."""
    report = MergeReport()
    steps = sorted(result.steps, key=lambda s: (s.t_start, s.t_end))
    if len(steps) < 2:
        return result, report
    index = {s.segment_id: s.index for s in segments}
    labels = {s.segment_id: s.data_classification for s in segments}
    ids = {f"s{i}": step for i, step in enumerate(steps, start=1)}
    listing = [
        {
            "id": sid,
            "segment": index.get(step.segment_id),
            "t_start": step.t_start,
            "t_end": step.t_end,
            "step": step.step,
            "actor": step.actor,
            "hand_action": step.hand_action,
            "objects": step.objects,
        }
        for sid, step in ids.items()
    ]
    prompt = render_prompt(
        "pass_c_merge.md",
        process_id=process_id,
        steps=json.dumps(listing, ensure_ascii=False, indent=1),
    )
    response = llm.generate(
        prompt,
        classification=strictest(labels[s.segment_id] for s in steps),
        json_schema=PASS_C_SCHEMA,
        temperature=0.0,
    )
    if response.usage:
        report.prompt_tokens = response.usage.prompt_tokens
        report.completion_tokens = response.usage.completion_tokens
    try:
        output = PassCOutput.model_validate(parse_json_object(response.text))
    except (InvalidJSONError, ValidationError) as exc:
        report.error = f"câu trả lời lượt C không hợp lệ, giữ nguyên bước: {exc}"
        output = PassCOutput(steps=[])
    merged, used = _apply(output, ids, index, report, threshold)
    leftovers = [step for sid, step in ids.items() if sid not in used]
    report.kept_unchanged = len(leftovers)
    final = sorted([*merged, *leftovers], key=lambda s: (s.t_start, s.t_end))
    _save(work_dir, prompt, response.model_dump(mode="json"), report)
    return result.model_copy(update={"steps": final}), report


def _apply(
    output: PassCOutput,
    ids: dict[str, TimedStep],
    index: dict[str, int],
    report: MergeReport,
    threshold: float,
) -> tuple[list[TimedStep], set[str]]:
    used: set[str] = set()
    merged: list[TimedStep] = []
    for item in output.steps:
        sources = [sid for sid in dict.fromkeys(item.source_ids) if sid in ids and sid not in used]
        if not sources:
            report.invented_dropped += 1
            log.info("Pass C: dropped a step with no known source: %r", item.step)
            continue
        parts = sorted((ids[sid] for sid in sources), key=lambda s: (s.t_start, s.t_end))
        segment_order = sorted({index.get(p.segment_id, 0) for p in parts})
        adjacent = all(b - a <= 1 for a, b in pairwise(segment_order))
        matches_a_source = any(similarity(item.step, p.step) >= threshold for p in parts)
        one_actor = len({p.actor for p in parts if p.actor}) <= 1
        if not (adjacent and matches_a_source and one_actor):
            report.rejected += 1
            log.info("Pass C: rejected %r (sources %s)", item.step, sources)
            continue
        used.update(sources)
        merged.append(_combine(item.step.strip(), parts))
        if len(parts) > 1:
            report.merged += 1
        elif item.step.strip() != parts[0].step:
            report.renamed += 1
    return merged, used


def _combine(name: str, parts: list[TimedStep]) -> TimedStep:
    first = parts[0]
    segment_ids = list(dict.fromkeys(sid for p in parts for sid in p.sources()))
    return first.model_copy(
        update={
            "step": name,
            # Who did it comes from the sources; the LLM has no say (it only merges and renames).
            "actor": next((p.actor for p in parts if p.actor), None),
            "t_start": min(p.t_start for p in parts),
            "t_end": max(p.t_end for p in parts),
            "hand_action": next((p.hand_action for p in parts if p.hand_action), None),
            "objects": list(dict.fromkeys(o for p in parts for o in p.objects)),
            "key_point_observed": next((p.key_point_observed for p in parts if p.key_point_observed), None),
            "confidence": round(sum(p.confidence for p in parts) / len(parts), 3),
            "keyframes": list(dict.fromkeys(k for p in parts for k in p.keyframes)),
            "segment_ids": segment_ids if len(segment_ids) > 1 else [],
        }
    )


def _save(work_dir: Path, prompt: str, response: dict[str, Any], report: MergeReport) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    record = {"prompt": prompt, "response": response, "report": report.model_dump()}
    (work_dir / "pass_c.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
