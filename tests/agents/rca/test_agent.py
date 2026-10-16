"""spec 06 T06-3 — RCA Agent: hypotheses with evidence, deterministic graph calls (AC-05..AC-08)."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from mentormind.agents.base import TraceLog
from mentormind.agents.rca import DISCLAIMER, RcaAgent
from mentormind.core.providers.llm.backends.fake import FakeLLM
from mentormind.core.schemas import DataClassification
from mentormind.core.schemas.agents import RcaRequest
from mentormind.knowledge_base.sigma.adapter import DefectRecord, LotNotFound, LotRecord
from tests.agents.fakes import REASON_PROFILE, FakeGraph, FakeRetriever, FakeSigma, context

LOT = LotRecord(
    lot_id="L-2026-0915-03", product_code="P-A", process_id="PACK01",
    date=date(2026, 9, 15), shift="B", operator_id="OP-07", qty=500,
)  # fmt: skip
D03 = DefectRecord(
    defect_id="DF-0007", lot_id=LOT.lot_id, process_id="PACK01", defect_code="D-03",
    description="Trầy bề mặt linh kiện", qty=12, detected_at=datetime(2026, 9, 15, 16, 30),
)  # fmt: skip
SYN = "synthetic"
# Rows as spec 05's HybridRetriever.run_template returns them.
GRAPH_ROWS: dict[str, list[dict[str, Any]]] = {
    "root_causes_of_symptom": [
        {"fact": "Nguyên nhân của Trầy bề mặt: Đặt linh kiện nằm ngang thay vì nghiêng",
         "source_type": "sigma", "ref_id": "defect_catalog.csv#D-03", "data_classification": [SYN, SYN]},
    ],
    "where_symptom_occurred": [
        {"fact": "Lô L-2026-0915-03 tại PACK01 có lỗi Trầy bề mặt", "source_type": "sigma",
         "ref_id": "L-2026-0915-03", "data_classification": [SYN, SYN, SYN]},
        {"fact": "Lô L-2026-0921-01 tại PACK01 có lỗi Trầy bề mặt", "source_type": "sigma",
         "ref_id": "L-2026-0921-01", "data_classification": [SYN, SYN, SYN]},
    ],
    "prevention_steps": [
        {"fact": "Bước phòng ngừa: Đặt linh kiện A vào ngăn trái", "source_type": "work_profile",
         "ref_id": "WP-PACK01-003", "data_classification": [SYN, SYN, SYN]},
    ],
}  # fmt: skip


def agent(llm: FakeLLM, tmp_path: Path) -> tuple[RcaAgent, FakeGraph, FakeRetriever]:
    graph = FakeGraph(GRAPH_ROWS, {"trầy": "D-03"})
    retriever = FakeRetriever(context((*REASON_PROFILE, 0.8, DataClassification.SYNTHETIC)))
    rca = RcaAgent(
        llm, graph, retriever, FakeSigma([LOT], [D03]),
        sigma_classification=DataClassification.SYNTHETIC, trace=TraceLog(tmp_path / "traces"),
    )  # fmt: skip
    return rca, graph, retriever


def answer(hypotheses: list[dict[str, Any]], five_why: list[dict[str, Any]]) -> str:
    return json.dumps({"hypotheses": hypotheses, "five_why": five_why}, ensure_ascii=False)


WHY: list[dict[str, Any]] = [
    {"why": "Vì sao linh kiện bị trầy?", "answer": "Va vào nắp khi đóng", "evidence_ids": [1]},
    {"why": "Vì sao va vào nắp?", "answer": "Linh kiện nằm ngang", "evidence_ids": [2]},
    {"why": "Vì sao nằm ngang?", "answer": "Thợ ca B chưa được hướng dẫn", "evidence_ids": []},
]


def test_ac_05_a_d03_lot_gets_hypotheses_backed_by_evidence(tmp_path: Path) -> None:
    llm = FakeLLM([answer(
        [{"cause": "Đặt linh kiện nằm ngang", "likelihood": "high", "evidence_ids": [2, 5],
          "check_actions": ["Quan sát thao tác đặt linh kiện ca B"]},
         {"cause": "Dao cắt thùng có ba via", "likelihood": "high", "evidence_ids": [],
          "check_actions": ["Kiểm tra dao"]}],
        WHY,
    )])  # fmt: skip
    report = agent(llm, tmp_path)[0].investigate(RcaRequest(lot_id=LOT.lot_id))
    assert report.hypotheses and report.disclaimer == DISCLAIMER
    for h in report.hypotheses:
        if h.likelihood in ("high", "medium"):
            assert h.evidence, h.cause
    unbacked = next(h for h in report.hypotheses if h.cause.startswith("Dao"))
    assert unbacked.likelihood == "low"  # no evidence, whatever the LLM claimed
    assert report.hypotheses[0].likelihood == "high"
    assert report.related_lots == ["L-2026-0921-01"] and report.prevention_steps == ["WP-PACK01-003"]


def test_ac_06_an_unknown_lot_raises_lot_not_found(tmp_path: Path) -> None:
    llm = FakeLLM([answer([], WHY)])
    with pytest.raises(LotNotFound):
        agent(llm, tmp_path)[0].investigate(RcaRequest(lot_id="KHONG-TON-TAI"))
    assert llm.calls == []


@pytest.mark.parametrize("layers", [2, 7])
def test_ac_07_five_why_has_3_to_5_levels_and_flags_unverified_ones(layers: int, tmp_path: Path) -> None:
    whys = [{"why": f"Vì sao {i}?", "answer": f"Do {i}", "evidence_ids": [1]} for i in range(layers)]
    llm = FakeLLM([answer([{"cause": "x", "likelihood": "low", "evidence_ids": []}], whys)])
    report = agent(llm, tmp_path)[0].investigate(RcaRequest(lot_id=LOT.lot_id))
    assert 3 <= len(report.five_why) <= 5
    if layers == 2:
        assert report.five_why[-1].verified is False  # padded level: to verify on the floor


def test_ac_07_a_level_without_evidence_is_unverified(tmp_path: Path) -> None:
    llm = FakeLLM([answer([], WHY)])
    report = agent(llm, tmp_path)[0].investigate(RcaRequest(lot_id=LOT.lot_id))
    assert [w.verified for w in report.five_why] == [True, True, False]


def test_ac_08_a_lot_calls_the_three_templates_by_name_never_the_router(tmp_path: Path) -> None:
    llm = FakeLLM([answer([], WHY)])
    rca, graph, retriever = agent(llm, tmp_path)
    rca.investigate(RcaRequest(lot_id=LOT.lot_id))
    assert sorted(t for t, _ in graph.calls) == [
        "prevention_steps", "root_causes_of_symptom", "where_symptom_occurred",
    ]  # fmt: skip
    assert all(params == {"symptom_id": "D-03"} for _, params in graph.calls)
    assert len(retriever.calls) == 1
    assert len(llm.calls) == 1  # the RCA prompt only: no router prompt went out


def test_a_symptom_text_is_mapped_by_the_spec05_matcher(tmp_path: Path) -> None:
    llm = FakeLLM([answer([], WHY)])
    rca, graph, _ = agent(llm, tmp_path)
    report = rca.investigate(RcaRequest(symptom_text="Linh kiện bị trầy", process_id="PACK01"))
    assert {params["symptom_id"] for _, params in graph.calls} == {"D-03"}
    assert report.lot_id is None and report.symptom == "Linh kiện bị trầy"


def test_an_unreadable_answer_falls_back_to_the_graph(tmp_path: Path) -> None:
    llm = FakeLLM(["không phải JSON", "vẫn không phải JSON"])
    report = agent(llm, tmp_path)[0].investigate(RcaRequest(lot_id=LOT.lot_id))
    assert len(llm.calls) == 2
    [h] = report.hypotheses
    assert h.cause == "Đặt linh kiện nằm ngang thay vì nghiêng" and h.evidence
    assert all(not w.verified for w in report.five_why) and len(report.five_why) == 3


def test_every_investigation_leaves_a_trace(tmp_path: Path) -> None:
    llm = FakeLLM([answer([], WHY)])
    agent(llm, tmp_path)[0].investigate(RcaRequest(lot_id=LOT.lot_id))
    [line] = (tmp_path / "traces").glob("rca-*.jsonl")
    assert "defect_catalog.csv#D-03" in line.read_text(encoding="utf-8")
