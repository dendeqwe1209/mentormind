"""What one golden-set run produces: per-question results, the summary, and their files."""

from __future__ import annotations

import csv
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from mentormind.core.schemas import DataClassification

RAGAS_METRICS = ("faithfulness", "answer_relevancy", "context_precision", "context_recall")
#: MVP thresholds of spec 09 §3B.
THRESHOLDS: dict[str, float] = {
    "faithfulness": 0.85,
    "answer_relevancy": 0.80,
    "context_precision": 0.70,
    "context_recall": 0.70,
}
RESULT_COLUMNS = [
    "qid",
    "process_id",
    "type",
    "refused",
    *RAGAS_METRICS,
    "citation_hit",
    "cited_ids",
    "expected_citations",
    "question",
    "answer",
]


class QuestionResult(BaseModel):
    qid: str
    process_id: str
    type: str
    question: str
    answer: str
    refused: bool
    cited_ids: list[str]
    expected_citations: list[str]
    citation_hit: bool | None = None
    scores: dict[str, float | None] = Field(default_factory=dict)


class EvalSummary(BaseModel):
    run_id: str
    started_at: datetime
    commit: str
    golden: str
    classification: DataClassification
    assistant_llm: str
    #: ``KNOWHOW_EVAL_JUDGE`` of the run (summaries written before it existed: ragas).
    judge: str = "ragas"
    judge_llm: str
    questions: int
    in_scope: int
    out_of_scope: int
    #: Means of the four Ragas metrics + ``refusal_accuracy`` + ``citation_hit_rate``.
    metrics: dict[str, float | None]
    thresholds: dict[str, float]
    out_of_scope_refused_rate: float | None
    in_scope_answered_rate: float | None
    judge_failures: int


def read_results(path: Path) -> list[QuestionResult]:
    """Rows of a ``ragas_results.csv`` written by :func:`run_golden` (for the report)."""
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return [
        QuestionResult(
            qid=r["qid"],
            process_id=r["process_id"],
            type=r["type"],
            question=r["question"],
            answer=r["answer"],
            refused=r["refused"] == "True",
            cited_ids=[x for x in r["cited_ids"].split("|") if x],
            expected_citations=[x for x in r["expected_citations"].split("|") if x],
            citation_hit=r["citation_hit"] == "True" if r["citation_hit"] else None,
            scores={m: float(r[m]) if r[m] else None for m in RAGAS_METRICS},
        )
        for r in rows
    ]


def write_rows(path: Path, results: Sequence[QuestionResult]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_COLUMNS)
        writer.writeheader()
        for r in results:
            writer.writerow(
                {
                    "qid": r.qid,
                    "process_id": r.process_id,
                    "type": r.type,
                    "refused": r.refused,
                    **{m: "" if r.scores.get(m) is None else round(r.scores[m] or 0.0, 3) for m in RAGAS_METRICS},
                    "citation_hit": "" if r.citation_hit is None else r.citation_hit,
                    "cited_ids": "|".join(r.cited_ids),
                    "expected_citations": "|".join(r.expected_citations),
                    "question": r.question,
                    "answer": r.answer,
                }
            )
