"""Pass A — describe each segment (spec 04 §3, T04-3).

For every :class:`Segment`: sample frames (FR-02b), ask the VLM with ``prompts/pass_a_describe.md``,
validate the answer against :data:`PASS_A_SCHEMA`; an invalid answer is retried ONCE with
``prompts/repair_json.md`` and, if still invalid, the segment goes to ``failed_segments.json``
while the other segments carry on (AC-06). Raw answers are kept under
``data/work/vlm/<video_id>/pass_a/`` (FR-06).

Where each step starts and ends is up to a :class:`~processing.vlm.passes.step_times.StepTimer`
(``KNOWHOW_VLM_STEP_TIMES``): by default the steps tile their segment in start order (AC-24), or
they keep the model's own spans clamped into the segment (AC-28).

With an ``executor`` (``KNOWHOW_VLM_CONCURRENCY`` > 1) the segments are described in parallel; the
result is the same as one at a time: steps in segment order, the same files (AC-30).

Post-processing into WorkProfiles lives in :mod:`processing.vlm.passes.postprocess`.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from concurrent.futures import Executor
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from mentormind.core.providers.errors import InvalidJSONError
from mentormind.core.providers.models import TokenUsage
from mentormind.core.providers.parsing import parse_json_object
from mentormind.core.providers.vlm.base import VLMProvider
from mentormind.core.providers.vlm.models import VLMResponse
from mentormind.core.schemas.video import Segment
from mentormind.processing.vlm.frames.sampler import SampledFrames, sample_frames
from mentormind.processing.vlm.passes.language import english_fields
from mentormind.processing.vlm.passes.models import (
    FailedSegment,
    PassAOutput,
    PassAResult,
    TimedStep,
)
from mentormind.processing.vlm.passes.parallel import wait_first_error
from mentormind.processing.vlm.passes.prompting import render_prompt
from mentormind.processing.vlm.passes.step_times import DEFAULT_STEP_TIMER, StepTimer

PASS_A_TEMPERATURE = 0.2
#: Repair reason when pass A answered in English (spec 04 §3): the steps become Vietnamese SOPs.
LANGUAGE_ERROR = "các trường chữ phải viết bằng tiếng Việt có dấu, đang là tiếng Anh ở {fields}"
log = logging.getLogger(__name__)

PASS_A_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        # Describe first, extract second: without it Qwen3-VL-8B answered {"steps": []} for every
        # segment of the demo video (spec 04 v1.5).
        "scene": {"type": "string"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "step": {"type": "string"},
                    "actor": {"enum": ["human", "robot", "machine", None]},
                    "hand_action": {"type": ["string", "null"]},
                    "objects": {"type": "array", "items": {"type": "string"}},
                    "key_point_observed": {"type": ["string", "null"]},
                    "t_start_rel": {"type": "number"},
                    "t_end_rel": {"type": "number"},
                    "confidence": {"type": "number"},
                },
                "required": ["step", "actor", "t_start_rel", "t_end_rel", "confidence"],
            },
        },
    },
    "required": ["scene", "steps"],
}

Sampler = Callable[..., SampledFrames]


def describe_segments(
    segments: Sequence[Segment],
    provider: VLMProvider,
    *,
    process_id: str,
    work_dir: Path,
    default_fps: float,
    max_frames: int,
    temperature: float = PASS_A_TEMPERATURE,
    sampler: Sampler = sample_frames,
    step_timer: StepTimer = DEFAULT_STEP_TIMER,
    executor: Executor | None = None,
) -> PassAResult:
    """Run pass A over ``segments`` (in order). Never raises for one bad segment.

    ``step_timer`` places each segment's steps in time (spec 04 §3; the callers pass
    ``get_step_timer(settings.vlm_step_times)``). ``executor`` describes the segments in parallel
    (its workers bound the requests in flight); the result is the one of the sequential loop (AC-30).
    """

    def describe(segment: Segment, into: PassAResult) -> None:
        _describe_one(
            segment,
            provider,
            into,
            process_id=process_id,
            work_dir=work_dir,
            default_fps=default_fps,
            max_frames=max_frames,
            temperature=temperature,
            sampler=sampler,
            step_timer=step_timer,
        )

    result = PassAResult()
    if executor is None:
        for segment in segments:
            describe(segment, result)
    else:
        parts = [PassAResult() for _ in segments]
        futures = [executor.submit(describe, segment, part) for segment, part in zip(segments, parts, strict=True)]
        wait_first_error(futures)  # an error a segment cannot absorb (e.g. DataGuard) stops the pass, as the loop
        for part in parts:
            _add(result, part)
    if result.failed:
        (work_dir / "failed_segments.json").write_text(
            json.dumps([f.model_dump() for f in result.failed], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return result


def _describe_one(
    segment: Segment,
    provider: VLMProvider,
    result: PassAResult,
    *,
    process_id: str,
    work_dir: Path,
    default_fps: float,
    max_frames: int,
    temperature: float,
    sampler: Sampler,
    step_timer: StepTimer,
) -> None:
    sampled = sampler(
        segment,
        provider,
        out_dir=work_dir / "frames" / segment.segment_id,
        default_fps=default_fps,
        max_frames=max_frames,
    )
    duration = max(segment.t_end - segment.t_start, 0.0)
    prompt = render_prompt(
        "pass_a_describe.md",
        process_id=process_id,
        duration=f"{duration:.1f}",
        fps=f"{sampled.fps:g}",
        timestamps=", ".join(f"{t:.1f}" for t in sampled.timestamps),
    )
    output: PassAOutput | None = None
    english: PassAOutput | None = None  # a valid answer in English, kept if the repair fails
    error = ""
    raw_text = ""
    for attempt in range(2):  # the answer, then at most ONE repair (spec 04 §3)
        text_prompt = prompt if attempt == 0 else render_prompt("repair_json.md", original_prompt=prompt, error=error)
        response = provider.generate(
            sampled.paths,
            text_prompt,
            classification=segment.data_classification,
            json_schema=PASS_A_SCHEMA,
            temperature=temperature,
        )
        _account(result, response)
        raw_text = response.text
        _save_raw(work_dir, segment, attempt, text_prompt, response, sampled)
        try:
            candidate = PassAOutput.model_validate(parse_json_object(response.text))
        except (InvalidJSONError, ValidationError) as exc:
            error = _short_error(exc)
            continue
        fields = english_fields(candidate)
        if fields and attempt == 0:
            english, error = candidate, LANGUAGE_ERROR.format(fields=", ".join(fields[:3]))
            continue
        if fields:
            log.warning("pass A %s still answered in English after the repair: %s", segment.segment_id, fields)
        output = candidate
        break
    output = output or english
    if output is None:
        result.failed.append(FailedSegment(segment_id=segment.segment_id, error=error, raw_text=raw_text))
        return
    if output.scene:
        result.scenes[segment.segment_id] = output.scene
    for step, start, end in step_timer.place(output.steps, segment):
        result.steps.append(
            TimedStep(
                segment_id=segment.segment_id,
                t_start=start,
                t_end=end,
                step=step.step.strip(),
                actor=step.actor,
                hand_action=step.hand_action,
                objects=step.objects,
                key_point_observed=step.key_point_observed,
                confidence=step.confidence,
                fps=sampled.fps,
                keyframes=list(segment.keyframes),
            )
        )


def _add(result: PassAResult, part: PassAResult) -> None:
    """Append one segment's pass-A result, as the sequential loop would have."""
    result.steps.extend(part.steps)
    result.failed.extend(part.failed)
    result.scenes.update(part.scenes)
    result.prompt_tokens += part.prompt_tokens
    result.completion_tokens += part.completion_tokens
    result.latency_s += part.latency_s
    result.calls += part.calls


def _account(result: PassAResult, response: VLMResponse) -> None:
    usage = response.usage or TokenUsage(prompt_tokens=0, completion_tokens=0)
    result.prompt_tokens += usage.prompt_tokens
    result.completion_tokens += usage.completion_tokens
    result.latency_s += response.latency_s
    result.calls += 1


def _save_raw(
    work_dir: Path,
    segment: Segment,
    attempt: int,
    prompt: str,
    response: VLMResponse,
    sampled: SampledFrames,
) -> None:
    raw_dir = work_dir / "pass_a"
    raw_dir.mkdir(parents=True, exist_ok=True)
    suffix = "" if attempt == 0 else ".repair"
    record = {
        "segment_id": segment.segment_id,
        "t_start": segment.t_start,
        "t_end": segment.t_end,
        "fps": sampled.fps,
        "frame_timestamps": sampled.timestamps,
        "prompt": prompt,
        "response": response.model_dump(mode="json"),
    }
    (raw_dir / f"{segment.segment_id}{suffix}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _short_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        first = exc.errors()[0]
        return f"sai schema tại {'/'.join(map(str, first['loc']))}: {first['msg']}"
    return "không phải JSON"
