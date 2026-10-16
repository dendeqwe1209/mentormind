"""spec 02b AC-06, AC-12, AC-13, AC-15, AC-16 on a real PostgreSQL + pgvector (`make up`).

Each test run works in a scratch table cloned from ``knowhow_chunks`` and drops it afterwards, so
the real table is never touched. Skipped when the database is unreachable.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import psycopg
import pytest

from mentormind.core.config import Settings
from mentormind.core.schemas.common import DataClassification
from mentormind.core.schemas.vector import VectorChunk
from mentormind.knowledge_base.store.pgvector_store import PgVectorStore
from mentormind.knowledge_base.store.vector_store import HashingEmbedder, VectorStoreError

pytestmark = pytest.mark.integration

DSN = Settings(_env_file=None).pg_dsn
DIM = 1024
PUBLIC, SYNTH, SECRET = (
    DataClassification.PUBLIC,
    DataClassification.SYNTHETIC,
    DataClassification.FACTORY_CONFIDENTIAL,
)
TABLE_MD = "| a | b |\n| --- | --- |\n| 1 | 2 |"


@pytest.fixture
def table() -> Iterator[str]:
    name = f"knowhow_chunks_t{uuid.uuid4().hex[:10]}"
    try:
        conn = psycopg.connect(DSN, connect_timeout=2)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL không chạy (make up)")
    with conn:
        conn.execute(f'CREATE TABLE "{name}" (LIKE public.knowhow_chunks INCLUDING ALL)')
    try:
        yield name
    finally:
        with psycopg.connect(DSN) as conn:
            conn.execute(f'DROP TABLE IF EXISTS "{name}"')


@pytest.fixture
def store(table: str) -> PgVectorStore:
    return PgVectorStore(DSN, table, HashingEmbedder(DIM))


def _chunk(cid: str, text: str, label: DataClassification = PUBLIC, **extra: object) -> VectorChunk:
    data: dict[str, object] = {
        "chunk_id": cid,
        "source_type": "document",
        "ref_id": cid.split("#")[0],
        "text": text,
        "data_classification": label,
    }
    data.update(extra)
    return VectorChunk.model_validate(data)


def _count(table: str) -> int:
    with psycopg.connect(DSN) as conn:
        row = conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()
    assert row is not None
    return int(row[0])


def _seed(store: PgVectorStore) -> None:
    store.upsert(
        [
            _chunk("DOC-aaaaaaaaaaaa#p1-0", "quy trình đóng gói PACK01", PUBLIC, process_ids=["PACK01"]),
            _chunk("DOC-aaaaaaaaaaaa#p1-1", TABLE_MD, PUBLIC, kind="table", process_ids=["PACK01"]),
            _chunk("DOC-bbbbbbbbbbbb#p1-0", "quy trình đóng gói PACK01", SYNTH, process_ids=["PACK01"]),
            _chunk("DOC-cccccccccccc#p1-0", "quy trình đóng gói", SECRET, kind="table", process_ids=["SOLD12"]),
        ]
    )


def _ids(store: PgVectorStore, **filters: object) -> set[str]:
    return {h.chunk.chunk_id for h in store.search("quy trình đóng gói", k=20, filters=filters or None)}


def test_ac_12_filter_public_never_returns_other_classes(store: PgVectorStore) -> None:
    _seed(store)
    hits = store.search("quy trình đóng gói", k=20, filters={"data_classification": ["public"]})
    assert hits and {h.chunk.data_classification for h in hits} == {PUBLIC}


def test_ac_06_filter_kind_table_returns_only_tables(store: PgVectorStore) -> None:
    _seed(store)
    assert _ids(store, kind="table") == {"DOC-aaaaaaaaaaaa#p1-1", "DOC-cccccccccccc#p1-0"}


def test_ac_13_kind_and_process_ids_combine_with_and(store: PgVectorStore) -> None:
    _seed(store)
    assert _ids(store, kind="table", process_ids="PACK01") == {"DOC-aaaaaaaaaaaa#p1-1"}
    assert _ids(store, process_ids=["SOLD12", "NOPE00"]) == {"DOC-cccccccccccc#p1-0"}


def test_set_filter_and_empty_set(store: PgVectorStore) -> None:
    _seed(store)
    assert len(_ids(store, data_classification=["public", "synthetic"])) == 3
    assert _ids(store, data_classification=[]) == set()


def test_doc_id_filter(store: PgVectorStore) -> None:
    _seed(store)
    assert _ids(store, doc_id="DOC-bbbbbbbbbbbb") == {"DOC-bbbbbbbbbbbb#p1-0"}


def test_ac_15_upsert_twice_count_unchanged(store: PgVectorStore, table: str) -> None:
    _seed(store)
    _seed(store)
    assert _count(table) == 4


def test_upsert_updates_text_and_metadata(store: PgVectorStore) -> None:
    _seed(store)
    store.upsert([_chunk("DOC-aaaaaaaaaaaa#p1-0", "hàn mạch SOLD12 nhiệt độ cao", metadata={"page": 7})])
    top = store.search("hàn mạch nhiệt độ", k=1)[0].chunk
    assert top.chunk_id == "DOC-aaaaaaaaaaaa#p1-0" and top.metadata == {"page": 7}


def test_roundtrip_keeps_every_field(store: PgVectorStore) -> None:
    store.upsert(
        [
            _chunk(
                "DOC-aaaaaaaaaaaa#p2-3",
                "chi tiết AA123456-7890",
                SECRET,
                kind="table",
                process_ids=["PACK01"],
                part_numbers=["AA123456-7890"],
                metadata={"title": "Tiêu đề", "page": 2},
            )
        ]
    )
    [hit] = store.search("chi tiết", k=3)
    c = hit.chunk
    assert (c.ref_id, c.kind, c.process_ids, c.part_numbers) == (
        "DOC-aaaaaaaaaaaa",
        "table",
        ["PACK01"],
        ["AA123456-7890"],
    )
    assert c.data_classification is SECRET and c.metadata == {"title": "Tiêu đề", "page": 2}


def test_lexical_match_ignores_vietnamese_accents(store: PgVectorStore) -> None:
    store.upsert(
        [
            _chunk("DOC-aaaaaaaaaaaa#p1-0", "tránh trầy bề mặt linh kiện"),
            _chunk("DOC-aaaaaaaaaaaa#p1-1", "kiểm tra nhãn hộp"),
        ]
    )
    assert store.search("tranh tray be mat", k=1)[0].chunk.chunk_id == "DOC-aaaaaaaaaaaa#p1-0"


def test_search_respects_k_and_scores_descend(store: PgVectorStore) -> None:
    _seed(store)
    hits = store.search("quy trình đóng gói", k=2)
    assert len(hits) == 2 and hits[0].score >= hits[1].score


def test_delete_returns_how_many_existed(store: PgVectorStore, table: str) -> None:
    _seed(store)
    assert store.delete(["DOC-aaaaaaaaaaaa#p1-0", "nope"]) == 1 and _count(table) == 3


def test_unknown_filter_key_never_reaches_sql(store: PgVectorStore) -> None:
    with pytest.raises(ValueError, match="Filter không hỗ trợ"):
        store.search("x", filters={'kind"; DROP TABLE x; --': "1"})


def test_filter_value_with_quotes_is_just_a_value(store: PgVectorStore, table: str) -> None:
    _seed(store)
    assert _ids(store, kind="x'; DROP TABLE y; --") == set() and _count(table) == 4


def test_ac_16_embed_dim_mismatch_fails_at_startup(table: str) -> None:
    with pytest.raises(VectorStoreError, match=r"vector\(1024\).*256"):
        PgVectorStore(DSN, table, HashingEmbedder(256))


def test_missing_table_is_a_clear_error(table: str) -> None:  # `table` only skips when the DB is down
    with pytest.raises(VectorStoreError, match="Không thấy bảng"):
        PgVectorStore(DSN, "no_such_table_xyz", HashingEmbedder(DIM))


def test_unreachable_database_is_a_clear_error() -> None:
    with pytest.raises(VectorStoreError, match="make up"):
        PgVectorStore("postgresql://x:y@127.0.0.1:1/z?connect_timeout=1", "knowhow_chunks", HashingEmbedder(DIM))


def test_delete_where_removes_one_document_only(store: PgVectorStore, table: str) -> None:
    _seed(store)
    assert store.delete_where({"source_type": "document", "doc_id": "DOC-aaaaaaaaaaaa"}) == 2
    assert _count(table) == 2 and store.delete_where({"doc_id": "DOC-aaaaaaaaaaaa"}) == 0


def test_delete_where_refuses_empty_filters(store: PgVectorStore, table: str) -> None:
    _seed(store)
    with pytest.raises(ValueError, match="filter"):
        store.delete_where({})
    assert _count(table) == 4
