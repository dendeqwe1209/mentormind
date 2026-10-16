"""spec 09 T09-4 — the usefulness report (AC-05, AC-06)."""

from __future__ import annotations

from datetime import UTC, datetime

from mentormind.core.schemas import DataClassification
from mentormind.evaluation.ragas import THRESHOLDS, EvalSummary, QuestionResult
from mentormind.evaluation.report import build_report, profiles_to_review
from mentormind.evaluation.review import ReviewStats


def summary(**metrics: float | None) -> EvalSummary:
    base: dict[str, float | None] = {
        "faithfulness": 0.9,
        "answer_relevancy": 0.7,
        "context_precision": 0.7,
        "context_recall": None,
        "refusal_accuracy": 0.8,
        "citation_hit_rate": 0.75,
    }
    base.update(metrics)
    return EvalSummary(
        run_id="r1",
        started_at=datetime(2026, 10, 1, tzinfo=UTC),
        commit="abc1234",
        golden="qa.jsonl",
        classification=DataClassification.SYNTHETIC,
        assistant_llm="fake",
        judge_llm="fake:judge",
        questions=5,
        in_scope=4,
        out_of_scope=1,
        metrics=base,
        thresholds=dict(THRESHOLDS),
        out_of_scope_refused_rate=1.0,
        in_scope_answered_rate=0.75,
        judge_failures=0,
    )


def result(qid: str, cited: list[str], expected: list[str], faith: float) -> QuestionResult:
    return QuestionResult(
        qid=qid,
        process_id="PACK01",
        type="why",
        question=f"Câu {qid}?",
        answer="…",
        refused=False,
        cited_ids=cited,
        expected_citations=expected,
        citation_hit=True,
        scores={
            "faithfulness": faith,
            "answer_relevancy": 0.9,
            "context_precision": 0.9,
            "context_recall": 0.9,
        },
    )


def row(report: str, name: str) -> str:
    return next(line for line in report.splitlines() if line.startswith(f"| {name} |"))


def test_ac_05_the_threshold_column_is_right_for_every_metric() -> None:
    report = build_report(summary(), [], None, [])
    assert row(report, "faithfulness").endswith("| 0.85 | ✅ |")
    assert row(report, "answer_relevancy").endswith("| 0.80 | ❌ |")
    assert row(report, "context_precision").endswith("| 0.70 | ✅ |")  # at the threshold passes
    assert row(report, "context_recall").endswith("| 0.70 | — |")  # no value, no verdict
    assert row(report, "refusal_accuracy").endswith("| — | — |")  # no threshold in spec 09


def test_ac_06_profiles_behind_two_weak_answers_are_listed_with_count_two() -> None:
    results = [
        result("Q001", ["WP-PACK01-003"], ["WP-PACK01-003"], faith=0.5),  # below threshold
        result("Q002", ["WP-PACK01-004"], ["WP-PACK01-003"], faith=0.4),  # below threshold
        result("Q003", ["WP-PACK01-003"], ["WP-PACK01-003"], faith=0.95),  # fine
    ]
    rows = profiles_to_review(results)
    assert rows[0] == ("WP-PACK01-003", "PACK01", 2)
    report = build_report(summary(), results, None, [])
    assert "| WP-PACK01-003 | PACK01 | 2 |" in report


def test_the_report_has_every_section_and_the_review_stats() -> None:
    stats = ReviewStats(
        events=10,
        approved_unchanged=0.4,
        approved_after_edit=0.2,
        rejected=0.4,
        error_tags={"missed_step": 3},
        reason_coverage={"synthetic": 0.6, "public": 0.0},
        reason_coverage_ok=True,
    )
    sweep = [{"fps": "4", "recall": "0.11", "precision": "0.15", "recall_time_only": "0.56"}]
    report = build_report(summary(), [result("Q001", [], [], 0.5)], stats, sweep)
    for heading in (
        "Chất lượng trả lời",
        "Trích xuất VLM",
        "Quét fps",
        "5 câu trả lời tệ nhất",
        "Profile cần xem lại",
        "Hạn chế",
        "Thiết kế thí nghiệm pilot",
    ):
        assert heading in report, heading
    assert "| reason_coverage (synthetic) | 0.60 | 0.60 | ✅ |" in report
