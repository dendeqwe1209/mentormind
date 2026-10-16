"""``knowhow eval ragas`` core (spec 09 FR-01, FR-05; T09-2).

Every golden question goes to the Work Assistant. Out-of-scope questions only test refusal and are
written apart (``out_of_scope.csv``); the others get the four Ragas metrics (contexts = the
snippets of the citations the answer carries) plus ``citation_hit``. A refused in-scope answer has
no Ragas scores (nothing to judge) and counts against ``refusal_accuracy``. Answers are collected
first, then the answered in-scope ones are judged in one ``Judge.score`` call.

Outputs in ``out_dir``: ``ragas_results.csv`` (one row per in-scope question), ``out_of_scope.csv``,
``summary.json`` (means, the two own metrics, thresholds, run id, time, models, commit).
"""

from __future__ import annotations

import subprocess
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from mentormind.core.config import REPO_ROOT
from mentormind.core.schemas import DataClassification
from mentormind.core.schemas.agents import AskRequest, AssistantAnswer
from mentormind.core.schemas.evaluation import GoldenQuestion
from mentormind.evaluation.ragas.judges import Judge, JudgeSample
from mentormind.evaluation.ragas.results import (
    RAGAS_METRICS,
    THRESHOLDS,
    EvalSummary,
    QuestionResult,
    write_rows,
)


class Answerer(Protocol):
    """What the runner asks: the spec 06 ``WorkAssistant`` (or a fake)."""

    def ask(self, request: AskRequest) -> AssistantAnswer: ...


def run_golden(
    questions: Sequence[GoldenQuestion],
    assistant: Answerer,
    judge: Judge,
    *,
    out_dir: Path,
    classification: DataClassification,
    golden_path: Path,
    assistant_llm: str = "",
) -> EvalSummary:
    """Run and score every question; write the three output files (spec 09 FR-01)."""
    started = datetime.now(UTC)
    answers = [(q, _ask(q, assistant)) for q in questions]
    results = [result for _, (result, _) in answers]
    judged = [(result, sample) for _, (result, sample) in answers if sample is not None]
    for (result, _), scores in zip(judged, judge.score([s for _, s in judged], classification), strict=True):
        result.scores = scores
    scored = [r for r in results if r.type != "out_of_scope"]
    oos = [r for r in results if r.type == "out_of_scope"]
    metrics: dict[str, float | None] = {name: _mean(r.scores.get(name) for r in scored) for name in RAGAS_METRICS}
    right = sum(r.refused for r in oos) + sum(not r.refused for r in scored)
    metrics["refusal_accuracy"] = _round(right / len(results)) if results else None
    metrics["citation_hit_rate"] = _mean(float(bool(r.citation_hit)) for r in scored)
    summary = EvalSummary(
        run_id=uuid.uuid4().hex[:12],
        started_at=started,
        commit=_commit(),
        golden=str(golden_path),
        classification=classification,
        assistant_llm=assistant_llm,
        judge=judge.kind,
        judge_llm=f"{judge.llm.name}:{judge.llm.model}",
        questions=len(results),
        in_scope=len(scored),
        out_of_scope=len(oos),
        metrics=metrics,
        thresholds=dict(THRESHOLDS),
        out_of_scope_refused_rate=_mean(float(r.refused) for r in oos),
        in_scope_answered_rate=_mean(float(not r.refused) for r in scored),
        judge_failures=judge.failures,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    write_rows(out_dir / "ragas_results.csv", scored)
    write_rows(out_dir / "out_of_scope.csv", oos)
    (out_dir / "summary.json").write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    return summary


def _ask(q: GoldenQuestion, assistant: Answerer) -> tuple[QuestionResult, JudgeSample | None]:
    """The question's result row, and what to judge when it is an answered in-scope question."""
    answer = assistant.ask(AskRequest(question=q.question, process_id=q.process_id))
    result = QuestionResult(
        qid=q.qid,
        process_id=q.process_id,
        type=q.type,
        question=q.question,
        answer=answer.answer,
        refused=answer.refused,
        cited_ids=[c.ref_id for c in answer.citations],
        expected_citations=list(q.expected_citations),
    )
    if q.type == "out_of_scope":
        return result, None
    result.citation_hit = bool(set(result.cited_ids) & set(q.expected_citations))
    if answer.refused:
        return result, None
    contexts = [c.snippet for c in answer.citations]
    return result, JudgeSample(q.question, answer.answer, contexts, q.ground_truth)


def _mean(values: object) -> float | None:
    numbers = [v for v in values if isinstance(v, float | int)]  # type: ignore[attr-defined]
    return _round(sum(numbers) / len(numbers)) if numbers else None


def _round(value: float) -> float:
    return round(value, 3)


def _commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
