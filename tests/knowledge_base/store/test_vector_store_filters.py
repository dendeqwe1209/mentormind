"""spec 02b AC-12, AC-13, AC-15 — filters and idempotent upsert on the memory backend."""

from __future__ import annotations

import pytest

from mentormind.core.schemas.common import DataClassification
from mentormind.core.schemas.vector import VectorChunk
from mentormind.knowledge_base.store.vector_store import MemoryVectorStore


def _chunk(cid: str, text: str, label: DataClassification, **extra: object) -> VectorChunk:
    data: dict[str, object] = {
        "chunk_id": cid,
        "source_type": "document",
        "ref_id": cid.split("#")[0],
        "text": text,
        "data_classification": label,
    }
    data.update(extra)
    return VectorChunk.model_validate(data)


PUBLIC, SYNTH, SECRET = (
    DataClassification.PUBLIC,
    DataClassification.SYNTHETIC,
    DataClassification.FACTORY_CONFIDENTIAL,
)
TABLE = "| a | b |\n| --- | --- |\n| 1 | 2 |"


def _store() -> MemoryVectorStore:
    store = MemoryVectorStore()
    store.upsert(
        [
            _chunk("DOC-aaaaaaaaaaaa#p1-0", "quy trình đóng gói PACK01", PUBLIC, process_ids=["PACK01"]),
            _chunk("DOC-aaaaaaaaaaaa#p1-1", TABLE, PUBLIC, kind="table", process_ids=["PACK01"]),
            _chunk("DOC-bbbbbbbbbbbb#p1-0", "quy trình đóng gói PACK01", SYNTH, process_ids=["PACK01"]),
            _chunk("DOC-cccccccccccc#p1-0", "quy trình đóng gói PACK01", SECRET, kind="table", process_ids=["SOLD12"]),
        ]
    )
    return store


def _ids(store: MemoryVectorStore, filters: dict[str, object]) -> set[str]:
    return {h.chunk.chunk_id for h in store.search("quy trình đóng gói", k=10, filters=filters)}


def test_ac_12_filter_public_never_returns_other_classes() -> None:
    hits = _store().search("quy trình đóng gói", k=10, filters={"data_classification": ["public"]})
    assert hits
    assert {h.chunk.data_classification for h in hits} == {PUBLIC}


def test_filter_classification_accepts_a_set_of_values() -> None:
    out = _ids(_store(), {"data_classification": ["public", "synthetic"]})
    assert out == {"DOC-aaaaaaaaaaaa#p1-0", "DOC-aaaaaaaaaaaa#p1-1", "DOC-bbbbbbbbbbbb#p1-0"}


def test_empty_value_list_matches_nothing() -> None:
    assert _ids(_store(), {"data_classification": []}) == set()


def test_ac_13_filter_kind_and_process_ids_and() -> None:
    assert _ids(_store(), {"kind": "table", "process_ids": "PACK01"}) == {"DOC-aaaaaaaaaaaa#p1-1"}


def test_process_ids_list_matches_any() -> None:
    out = _ids(_store(), {"process_ids": ["SOLD12", "OTHER99"]})
    assert out == {"DOC-cccccccccccc#p1-0"}


def test_doc_id_filter() -> None:
    assert _ids(_store(), {"doc_id": "DOC-bbbbbbbbbbbb"}) == {"DOC-bbbbbbbbbbbb#p1-0"}


def test_unknown_filter_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="Filter không hỗ trợ"):
        _store().search("x", filters={"text; DROP TABLE": "1"})


def test_ac_15_upsert_twice_no_duplicates() -> None:
    store = _store()
    again = [
        _chunk("DOC-aaaaaaaaaaaa#p1-0", "quy trình đóng gói PACK01", PUBLIC, process_ids=["PACK01"]),
    ]
    store.upsert(again)
    store.upsert(again)
    assert len(_ids(store, {})) == 4


def test_upsert_updates_text_and_reembeds() -> None:
    store = _store()
    store.upsert([_chunk("DOC-aaaaaaaaaaaa#p1-0", "hàn mạch SOLD12 nhiệt độ cao", PUBLIC)])
    top = store.search("hàn mạch nhiệt độ", k=1)[0].chunk
    assert top.chunk_id == "DOC-aaaaaaaaaaaa#p1-0" and "SOLD12" in top.text


def test_search_respects_k() -> None:
    assert len(_store().search("quy trình", k=2)) == 2


def test_delete_where_removes_only_the_matching_chunks_and_counts_them() -> None:
    store = _store()
    assert store.delete_where({"doc_id": "DOC-aaaaaaaaaaaa"}) == 2
    left = {h.chunk.chunk_id for h in store.search("quy trình đóng gói PACK01", k=20)}
    assert left == {"DOC-bbbbbbbbbbbb#p1-0", "DOC-cccccccccccc#p1-0"}
    assert store.delete_where({"doc_id": "DOC-aaaaaaaaaaaa"}) == 0


def test_delete_where_combines_filters_with_and() -> None:
    store = _store()
    assert store.delete_where({"doc_id": "DOC-cccccccccccc", "kind": "text"}) == 0
    assert store.delete_where({"doc_id": "DOC-cccccccccccc", "kind": "table"}) == 1


def test_delete_where_refuses_empty_filters_so_the_table_is_never_wiped() -> None:
    store = _store()
    with pytest.raises(ValueError, match="filter"):
        store.delete_where({})
    assert len(store.search("quy trình", k=20)) == 4
