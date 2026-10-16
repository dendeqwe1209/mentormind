"""``knowhow eval report`` (spec 09 FR-04; T09-4): one markdown usefulness report.

Sections: answer quality against the thresholds (✅/❌), VLM extraction (review stats, fps sweep),
the five worst answers with why, the profiles to review (those cited by, or expected for, answers
below a threshold — input for spec 08's correction loop), limits, and the pilot design (group C,
no numbers invented).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence

from mentormind.evaluation.ragas import (
    RAGAS_METRICS,
    THRESHOLDS,
    EvalSummary,
    QuestionResult,
)
from mentormind.evaluation.report.sections import LIMITS, PILOT
from mentormind.evaluation.review import ReviewStats

OWN_METRICS = ("refusal_accuracy", "citation_hit_rate")
_SWEEP_COLUMNS = (
    "fps",
    "recall",
    "precision",
    "recall_time_only",
    "order_accuracy",
    "key_point_recall",
    "actor_accuracy",
    "tokens_used",
)


def build_report(
    summary: EvalSummary,
    results: Sequence[QuestionResult],
    stats: ReviewStats | None,
    sweep: Sequence[Mapping[str, str]],
) -> str:
    lines = [
        "# Báo cáo mức độ hữu ích — Mentor Mind",
        "",
        f"Lần chạy `{summary.run_id}` · {summary.started_at:%Y-%m-%d %H:%M} UTC · commit "
        f"`{summary.commit}` · trợ lý `{summary.assistant_llm or '?'}` · "
        f"judge `{summary.judge}` (`{summary.judge_llm}`) · {summary.questions} câu "
        f"({summary.in_scope} trong phạm vi, {summary.out_of_scope} ngoài phạm vi).",
        "",
        "## Chất lượng trả lời (nhóm B)",
        "",
        "| Chỉ số | Giá trị | Ngưỡng | Đạt ngưỡng |",
        "|---|---|---|---|",
    ]
    for name in (*RAGAS_METRICS, *OWN_METRICS):
        value = summary.metrics.get(name)
        threshold = summary.thresholds.get(name)
        lines.append(f"| {name} | {_num(value)} | {_num(threshold)} | {_verdict(value, threshold)} |")
    lines += ["", *_extraction(stats, sweep), *_worst(results, summary), *_review_table(results)]
    lines += [*LIMITS, *PILOT]
    return "\n".join(lines) + "\n"


def profiles_to_review(
    results: Sequence[QuestionResult], thresholds: Mapping[str, float] | None = None
) -> list[tuple[str, str, int]]:
    """``(profile_id, process_id, number of weak answers)``, most-involved first (AC-06)."""
    questions: dict[tuple[str, str], set[str]] = defaultdict(set)
    for r in results:
        if not _weak(r, thresholds):
            continue
        for ref in {*r.cited_ids, *r.expected_citations}:
            if ref.startswith("WP-"):
                questions[(ref, r.process_id)].add(r.qid)
    return sorted(
        ((pid, proc, len(qids)) for (pid, proc), qids in questions.items()),
        key=lambda row: (-row[2], row[0]),
    )


def _extraction(stats: ReviewStats | None, sweep: Sequence[Mapping[str, str]]) -> list[str]:
    out = ["## Trích xuất VLM (nhóm A)", ""]
    if stats is None:
        out += ["_Chưa có dữ liệu duyệt (profile store của spec 08)._", ""]
    else:
        out += [
            f"{stats.events} lượt duyệt: duyệt không sửa {_pct(stats.approved_unchanged)}, "
            f"duyệt sau khi sửa {_pct(stats.approved_after_edit)}, "
            f"từ chối {_pct(stats.rejected)}.",
            "",
            "| Lỗi (error_tags) | Số lần |",
            "|---|---|",
            *[f"| {tag} | {count} |" for tag, count in stats.error_tags.items()],
            "",
            "| Chỉ số | Giá trị | Ngưỡng | Đạt ngưỡng |",
            "|---|---|---|---|",
        ]
        for label, value in stats.reason_coverage.items():
            if label == "synthetic":
                threshold = stats.reason_coverage_threshold
                out.append(
                    f"| reason_coverage (synthetic) | {_num(value)} | {_num(threshold)} | "
                    f"{_verdict(value, threshold)} |"
                )
            else:
                out.append(f"| reason_coverage ({label}) | {_num(value)} | — | chỉ báo cáo |")
        out.append("")
    out += ["### Quét fps (spec 04)", ""]
    if not sweep:
        out += ["_Không có CSV sweep._", ""]
    else:
        columns = [
            c
            for c in (
                "fps",
                "recall",
                "precision",
                "recall_time_only",
                "order_accuracy",
                "key_point_recall",
                "actor_accuracy",
                "tokens_used",
            )
            if c in sweep[0]
        ]
        out += ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
        out += ["| " + " | ".join(row.get(c, "") for c in columns) + " |" for row in sweep]
        out.append("")
    return out


def _worst(results: Sequence[QuestionResult], summary: EvalSummary) -> list[str]:
    ranked = sorted(results, key=_quality)[:5]
    out = ["## 5 câu trả lời tệ nhất", ""]
    if not ranked:
        return [*out, "_Không có câu nào._", ""]
    out += ["| qid | Câu hỏi | Điểm TB | Vì sao |", "|---|---|---|---|"]
    for r in ranked:
        out.append(f"| {r.qid} | {r.question} | {_num(_quality(r))} | {_why(r, summary.thresholds)} |")
    return [*out, ""]


def _review_table(results: Sequence[QuestionResult]) -> list[str]:
    rows = profiles_to_review(results)
    out = [
        "## Profile cần xem lại",
        "",
        "Profile được trích hoặc được kỳ vọng trong những câu dưới ngưỡng (đầu vào cho vòng sửa ở spec 08).",
        "",
    ]
    if not rows:
        return [*out, "_Không có._", ""]
    out += ["| profile_id | process_id | Số câu liên quan |", "|---|---|---|"]
    out += [f"| {pid} | {proc} | {count} |" for pid, proc, count in rows]
    return [*out, ""]


def _weak(r: QuestionResult, thresholds: Mapping[str, float] | None = None) -> bool:
    limits = thresholds or THRESHOLDS
    if r.type == "out_of_scope":
        return False
    if r.refused or r.citation_hit is False:
        return True
    return any(v is not None and v < limits[m] for m, v in r.scores.items() if m in limits)


def _quality(r: QuestionResult) -> float:
    if r.refused:
        return 0.0
    values = [v for v in r.scores.values() if v is not None]
    return sum(values) / len(values) if values else 0.0


def _why(r: QuestionResult, thresholds: Mapping[str, float]) -> str:
    if r.refused:
        return "trợ lý từ chối dù câu trong phạm vi"
    reasons = [
        f"{m} {v:.2f} < {thresholds[m]:.2f}"
        for m, v in r.scores.items()
        if v is not None and m in thresholds and v < thresholds[m]
    ]
    if r.citation_hit is False:
        reasons.append("không trích nguồn kỳ vọng")
    return "; ".join(reasons) or "đạt ngưỡng"


def _verdict(value: float | None, threshold: float | None) -> str:
    if value is None or threshold is None:
        return "—"
    return "✅" if value >= threshold else "❌"


def _num(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.0%}"
