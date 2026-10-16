"""spec 09 T09-2 — golden-set runner, Ragas metrics and the two own metrics (AC-02, AC-03)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from mentormind.core.schemas import DataClassification
from mentormind.evaluation.golden import load_golden
from mentormind.evaluation.ragas import RAGAS_METRICS, EvalSummary, RagasJudge, run_golden
from tests.evaluation.fakes import REFUSED, SameVectorEmbedder, ScriptedAssistant, ScriptedJudge, answered

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "eval" / "qa_5.jsonl"


def assistant(*, refuse_q003: bool = False) -> ScriptedAssistant:
    questions = {q.qid: q.question for q in load_golden(FIXTURE)}
    return ScriptedAssistant(
        {
            questions["Q001"]: answered("Ngăn trái, đặt nghiêng [1].", ["WP-PACK01-003"]),
            questions["Q002"]: answered("Để tránh trầy [1].", ["WP-PACK01-003"]),
            questions["Q003"]: REFUSED if refuse_q003 else answered("Báo ca [1].", ["WP-PACK01-099"]),
            questions["Q004"]: answered("Lot L-2026-0915-03 [1].", ["WP-PACK01-004"]),
            questions["Q005"]: REFUSED,
        }
    )


def run(tmp_path: Path, **kwargs: bool) -> EvalSummary:
    return run_golden(
        load_golden(FIXTURE),
        assistant(**kwargs),
        RagasJudge(ScriptedJudge(), SameVectorEmbedder()),
        out_dir=tmp_path,
        classification=DataClassification.SYNTHETIC,
        golden_path=FIXTURE,
    )


def test_ac_02_four_scored_rows_the_out_of_scope_one_apart_and_a_full_summary(
    tmp_path: Path,
) -> None:
    run(tmp_path)
    with (tmp_path / "ragas_results.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [r["qid"] for r in rows] == ["Q001", "Q002", "Q003", "Q004"]
    with (tmp_path / "out_of_scope.csv").open(encoding="utf-8") as handle:
        assert [r["qid"] for r in csv.DictReader(handle)] == ["Q005"]
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    for name in (*RAGAS_METRICS, "refusal_accuracy", "citation_hit_rate"):
        assert summary["metrics"][name] is not None, name
    assert summary["metrics"]["faithfulness"] == 0.75  # 3 of 4 claims supported
    assert summary["metrics"]["context_precision"] == 1.0  # the only useful context ranks first
    assert summary["metrics"]["answer_relevancy"] == 1.0
    assert summary["metrics"]["citation_hit_rate"] == 0.75  # Q001, Q002, Q004 hit; Q003 misses
    for key in ("run_id", "started_at", "commit", "assistant_llm", "judge", "judge_llm"):
        assert key in summary  # FR-05
    assert summary["judge"] == "ragas"


def test_ac_03_refusal_accuracy_counts_both_kinds_of_right_decision(tmp_path: Path) -> None:
    summary = run(tmp_path, refuse_q003=True)
    # Right: Q001, Q002, Q004 answered (in scope) + Q005 refused (out of scope). Wrong: Q003.
    assert summary.metrics["refusal_accuracy"] == 0.8
    assert summary.out_of_scope_refused_rate == 1.0 and summary.in_scope_answered_rate == 0.75


def test_a_factory_label_never_reaches_a_cloud_judge(tmp_path: Path) -> None:
    from mentormind.core.guard import ConfidentialDataError, GuardPolicy

    judge_llm = ScriptedJudge(name="qwen_api", is_cloud=True)
    judge_llm.guard_policy = GuardPolicy(audit_dir=None)
    with pytest.raises(ConfidentialDataError):
        run_golden(
            load_golden(FIXTURE),
            assistant(),
            RagasJudge(judge_llm, SameVectorEmbedder()),
            out_dir=tmp_path,
            classification=DataClassification.FACTORY_CONFIDENTIAL,
            golden_path=FIXTURE,
        )
