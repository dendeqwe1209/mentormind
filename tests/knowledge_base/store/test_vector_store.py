"""spec 01 FR-05c / AC-08 — VectorStore interface, memory backend and the config factory."""

from __future__ import annotations

import pytest

from mentormind.core.config import Settings
from mentormind.core.schemas.common import DataClassification
from mentormind.core.schemas.vector import VectorChunk
from mentormind.knowledge_base.store.vector_store import (
    HashingEmbedder,
    MemoryVectorStore,
    VectorStoreError,
    get_vector_store,
    tokens,
)


def chunk(cid: str, text: str, **extra: object) -> VectorChunk:
    data: dict[str, object] = {
        "chunk_id": cid,
        "source_type": "document",
        "ref_id": cid.split("#")[0],
        "text": text,
        "data_classification": DataClassification.SYNTHETIC,
    }
    data.update(extra)
    return VectorChunk.model_validate(data)


CHUNKS = [
    chunk("DOC-1#p1-0", "Đặt linh kiện A nghiêng để tránh trầy bề mặt", process_ids=["PACK01"]),
    chunk("DOC-1#p1-1", "| Bước | Kiểm tra |\n| 1 | khe hở 2mm |", kind="table"),
    chunk(
        "WP-PACK01-003",
        "Báo quản lý ca khi thiếu linh kiện",
        source_type="work_profile",
        ref_id="WP-PACK01-003",
        process_ids=["PACK01"],
    ),
]


def test_ac_08_memory_backend_works_without_docker() -> None:
    store = get_vector_store(Settings(_env_file=None, vector_backend="memory"))
    assert store.upsert(CHUNKS) == 3
    hits = store.search("tránh trầy", k=2)
    assert hits and hits[0].chunk.chunk_id == "DOC-1#p1-0"


def test_upsert_by_chunk_id_never_duplicates() -> None:
    store = MemoryVectorStore()
    store.upsert(CHUNKS)
    store.upsert([chunk("DOC-1#p1-0", "nội dung mới")])
    hits = store.search("nội dung mới", k=10)
    assert len(hits) == 3
    assert hits[0].chunk.text == "nội dung mới"


def test_filters_on_kind_source_type_and_process() -> None:
    store = MemoryVectorStore()
    store.upsert(CHUNKS)
    assert [h.chunk.chunk_id for h in store.search("bước", filters={"kind": "table"})] == ["DOC-1#p1-1"]
    profiles = store.search("linh kiện", filters={"source_type": "work_profile"})
    assert [h.chunk.ref_id for h in profiles] == ["WP-PACK01-003"]
    assert {h.chunk.chunk_id for h in store.search("x", filters={"process_id": "PACK01"})} == {
        "DOC-1#p1-0",
        "WP-PACK01-003",
    }
    with pytest.raises(ValueError, match="không hỗ trợ"):
        store.search("x", filters={"colour": "red"})


def test_lexical_match_ignores_vietnamese_accents() -> None:
    assert tokens("Tránh TRẦY, đóng nắp") == ["tranh", "tray", "dong", "nap"]
    store = MemoryVectorStore()
    store.upsert(CHUNKS)
    assert store.search("tranh tray", k=1)[0].chunk.chunk_id == "DOC-1#p1-0"


def test_delete_returns_how_many_existed() -> None:
    store = MemoryVectorStore()
    store.upsert(CHUNKS)
    assert store.delete(["WP-PACK01-003", "missing"]) == 1
    assert all(h.chunk.chunk_id != "WP-PACK01-003" for h in store.search("thiếu linh kiện"))


def test_embedding_of_the_wrong_size_is_refused() -> None:
    store = MemoryVectorStore(HashingEmbedder(dim=8))
    with pytest.raises(VectorStoreError, match="chiều"):
        store.upsert([chunk("DOC-2#p1-0", "x", embedding=[0.1, 0.2])])
