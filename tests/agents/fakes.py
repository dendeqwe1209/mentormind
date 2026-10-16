"""Fakes of the spec 05 / spec 07 ports for the agent tests."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from mentormind.core.schemas import Citation, DataClassification
from mentormind.knowledge_base.retrieval.hybrid import RetrievedContext
from mentormind.knowledge_base.sigma.adapter import DefectRecord, LotNotFound, LotRecord

REASON_PROFILE = (
    "WP-PACK01-003",
    "Bước: Đặt linh kiện A vào ngăn trái. Thao tác: tay phải xoay 90 độ, đặt nghiêng. "
    "Lý do: tránh trầy bề mặt khi đóng nắp hộp. Ngoại lệ: thiếu 1 món thì báo quản lý ca.",
)


def context(
    *items: tuple[str, str, float, DataClassification], query: str = "q", process: str = "PACK01"
) -> RetrievedContext:
    return RetrievedContext(
        query=query,
        process_id=process,
        passages=[text for _, text, _, _ in items],
        citations=[
            Citation(source_type="work_profile", ref_id=ref, snippet=text[:80], score=score)
            for ref, text, score, _ in items
        ],
        graph_facts=[],
        classifications=[label for *_, label in items],
    )


class FakeRetriever:
    def __init__(self, result: RetrievedContext) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def retrieve(self, query: str, process_id: str | None = None, k: int = 8) -> RetrievedContext:
        self.calls.append({"query": query, "process_id": process_id, "k": k})
        return self.result


class FakeExperts:
    def __init__(self, names: dict[str, str]) -> None:
        self.names = names

    def top_contributor(self, process_id: str) -> str | None:
        return self.names.get(process_id)


class FakeGraph:
    def __init__(self, rows: dict[str, list[dict[str, Any]]], symptoms: dict[str, str]) -> None:
        self.rows = rows
        self.symptoms = symptoms
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run_template(self, template: str, **params: Any) -> list[dict[str, Any]]:
        self.calls.append((template, params))
        return self.rows.get(template, [])

    def match_symptom(self, text: str) -> str | None:
        return next((sid for word, sid in self.symptoms.items() if word in text.lower()), None)


class FakeSigma:
    def __init__(self, lots: list[LotRecord], defects: list[DefectRecord]) -> None:
        self.lots = {lot.lot_id: lot for lot in lots}
        self.defects = defects

    def get_lot(self, lot_id: str) -> LotRecord:
        if lot_id not in self.lots:
            raise LotNotFound(lot_id)
        return self.lots[lot_id]

    def get_defects(self, lot_id: str) -> list[DefectRecord]:
        return [d for d in self.defects if d.lot_id == lot_id]


class FakeEmbedder:
    """bge-m3 stand-in: texts about packing point one way, anything else at right angles (cosine 0)."""

    TOPIC = ("hộp", "thùng", "linh kiện", "sản phẩm", "nắp", "đặt", "bỏ", "nghiêng", "xếp")

    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        return [[1.0, 0.0] if any(w in t.lower() for w in self.TOPIC) else [0.0, 1.0] for t in texts]


def reply(answer: str, used: Sequence[int], *, answerable: bool = True) -> dict[str, Any]:
    """The Work Assistant's JSON answer (spec 06 §3 guard 3)."""
    return {"answerable": answerable, "answer": answer, "used_sources": list(used)}
