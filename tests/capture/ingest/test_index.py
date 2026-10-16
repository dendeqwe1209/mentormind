"""spec 02 FR-07, AC-14, AC-15 — chunk files -> VectorStore."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from mentormind.capture.ingest import cli as ingest_cli
from mentormind.capture.ingest.index import index_chunks, index_files, replace_docs
from mentormind.capture.ingest.jsonl import write_chunks_atomic
from mentormind.core.cli import app
from mentormind.core.schemas import ChunkKind, DataClassification, DocumentChunk
from mentormind.core.schemas.vector import VectorChunk, VectorHit
from mentormind.knowledge_base.store.vector_store import MemoryVectorStore, VectorStoreError

TABLE = "| a | b |\n| --- | --- |\n| 1 | 2 |"


def _chunk(doc: str, i: int, label: DataClassification = DataClassification.PUBLIC, **over: Any) -> DocumentChunk:
    base: dict[str, Any] = {
        "chunk_id": f"DOC-{doc * 12}#p1-{i}",
        "doc_id": f"DOC-{doc * 12}",
        "source_path": f"{doc}.pdf",
        "title": "Tiêu đề",
        "page": 1,
        "kind": ChunkKind.TEXT,
        "text": f"đoạn {i} công đoạn PACK01",
        "process_ids": ["PACK01"],
        "part_numbers": ["AA123456-7890"],
        "data_classification": label,
        "extractor": "docling",
        "metadata": {"heading": "Mục 1"},
    }
    base.update(over)
    return DocumentChunk(**base)


def _all(store: MemoryVectorStore, filters: Mapping[str, Any] | None = None) -> list[VectorHit]:
    return store.search("công đoạn PACK01", k=100, filters=filters)


def test_index_maps_fields_to_vectorchunk(tmp_path: Path) -> None:
    write_chunks_atomic(tmp_path / "a.jsonl", [_chunk("a", 0, kind=ChunkKind.TABLE, text=TABLE)])
    store = MemoryVectorStore()
    result = index_chunks(tmp_path, store)
    [hit] = _all(store)
    got = hit.chunk
    assert (result.upserted, result.files_ok, result.files_failed) == (1, 1, [])
    assert got.chunk_id == "DOC-aaaaaaaaaaaa#p1-0" and got.source_type == "document"
    assert got.ref_id == "DOC-aaaaaaaaaaaa" and got.kind == "table" and got.text == TABLE
    assert got.process_ids == ["PACK01"] and got.part_numbers == ["AA123456-7890"]
    assert got.data_classification is DataClassification.PUBLIC
    assert got.metadata == {
        "page": 1,
        "title": "Tiêu đề",
        "source_path": "a.pdf",
        "extractor": "docling",
        "heading": "Mục 1",
    }


def test_ac_15_index_twice_same_count(tmp_path: Path) -> None:
    write_chunks_atomic(tmp_path / "a.jsonl", [_chunk("a", 0), _chunk("a", 1)])
    store = MemoryVectorStore()
    index_chunks(tmp_path, store)
    index_chunks(tmp_path, store)
    assert len(_all(store)) == 2


def test_ac_14_bad_line_writes_nothing_for_that_file_and_others_continue(tmp_path: Path) -> None:
    write_chunks_atomic(tmp_path / "a.jsonl", [_chunk("a", 0)])
    write_chunks_atomic(tmp_path / "b.jsonl", [_chunk("b", 0), _chunk("b", 1)])
    bad = tmp_path / "b.jsonl"
    bad.write_text(bad.read_text() + '{"chunk_id": "nope"}\n')
    store = MemoryVectorStore()
    result = index_chunks(tmp_path, store)
    assert {h.chunk.ref_id for h in _all(store)} == {"DOC-aaaaaaaaaaaa"}
    assert result.files_ok == 1 and result.upserted == 1
    [(name, why)] = result.files_failed
    assert name == "b.jsonl" and "dòng 3" in why


def test_classification_and_kind_are_filterable_after_index(tmp_path: Path) -> None:
    write_chunks_atomic(
        tmp_path / "a.jsonl",
        [_chunk("a", 0), _chunk("a", 1, kind=ChunkKind.TABLE, text=TABLE)],
    )
    write_chunks_atomic(tmp_path / "b.jsonl", [_chunk("b", 0, DataClassification.FACTORY_CONFIDENTIAL)])
    store = MemoryVectorStore()
    index_chunks(tmp_path, store)
    public = _all(store, {"data_classification": ["public"]})
    assert {h.chunk.ref_id for h in public} == {"DOC-aaaaaaaaaaaa"} and len(public) == 2
    assert [h.chunk.chunk_id for h in _all(store, {"kind": "table"})] == ["DOC-aaaaaaaaaaaa#p1-1"]


class _Spy:
    def __init__(self) -> None:
        self.batches: list[int] = []

    def upsert(self, chunks: Iterable[VectorChunk]) -> int:
        batch = list(chunks)
        self.batches.append(len(batch))
        return len(batch)

    def search(self, query: str, k: int = 8, filters: Mapping[str, Any] | None = None) -> list[VectorHit]:
        return []

    def delete(self, ids: Iterable[str]) -> int:
        return 0

    def delete_where(self, filters: Mapping[str, Any]) -> int:
        return 0


def test_upsert_is_batched(tmp_path: Path) -> None:
    write_chunks_atomic(tmp_path / "a.jsonl", [_chunk("a", i) for i in range(5)])
    spy = _Spy()
    index_chunks(tmp_path, spy, batch_size=2)
    assert spy.batches == [2, 2, 1]


def test_batch_size_must_be_positive(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="batch_size"):
        index_chunks(tmp_path, _Spy(), batch_size=0)


def test_missing_directory_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        index_chunks(tmp_path / "nope", _Spy())


def test_empty_directory_is_a_noop(tmp_path: Path) -> None:
    result = index_chunks(tmp_path, _Spy())
    assert (result.upserted, result.files_ok, result.files_failed) == (0, 0, [])


def test_index_files_upserts_only_the_given_files(tmp_path: Path) -> None:
    # The upload API (spec 08 §2) indexes the chunk files of one upload, not the whole folder.
    write_chunks_atomic(tmp_path / "a.jsonl", [_chunk("a", 0)])
    write_chunks_atomic(tmp_path / "b.jsonl", [_chunk("b", 0), _chunk("b", 1)])
    store = MemoryVectorStore()
    result = index_files([tmp_path / "b.jsonl"], store)
    assert (result.upserted, result.files_ok, result.doc_ids) == (2, 1, {"DOC-bbbbbbbbbbbb"})
    assert {h.chunk.ref_id for h in _all(store)} == {"DOC-bbbbbbbbbbbb"}


def test_index_files_rejects_a_bad_file_whole_and_checks_batch_size(tmp_path: Path) -> None:
    (tmp_path / "a.jsonl").write_text("not json\n")
    result = index_files([tmp_path / "a.jsonl"], _Spy())
    assert result.upserted == 0 and [name for name, _ in result.files_failed] == ["a.jsonl"]
    with pytest.raises(ValueError, match="batch_size"):
        index_files([], _Spy(), batch_size=0)


runner = CliRunner()


def test_cli_index_reports_totals(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_chunks_atomic(tmp_path / "a.jsonl", [_chunk("a", 0), _chunk("a", 1)])
    store = MemoryVectorStore()
    monkeypatch.setattr(ingest_cli, "build_store", lambda settings: store)
    result = runner.invoke(app, ["ingest", "index", "--chunks", str(tmp_path)])
    assert result.exit_code == 0 and "2 chunk" in result.output and len(_all(store)) == 2


def test_cli_index_exits_nonzero_when_a_file_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "a.jsonl").write_text("not json\n")
    monkeypatch.setattr(ingest_cli, "build_store", lambda settings: MemoryVectorStore())
    result = runner.invoke(app, ["ingest", "index", "--chunks", str(tmp_path)])
    assert result.exit_code == 1 and "a.jsonl" in result.output


def test_cli_index_backend_unavailable_is_a_clear_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(settings: object) -> None:
        raise VectorStoreError("Backend pgvector chưa có")

    monkeypatch.setattr(ingest_cli, "build_store", boom)
    result = runner.invoke(app, ["ingest", "index", "--chunks", str(tmp_path)])
    assert result.exit_code == 2 and "pgvector" in result.output


def test_cli_index_missing_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ingest_cli, "build_store", lambda settings: MemoryVectorStore())
    result = runner.invoke(app, ["ingest", "index", "--chunks", str(tmp_path / "nope")])
    assert result.exit_code == 2 and "nope" in result.output


def _store_with_old_doc(tmp_path: Path) -> MemoryVectorStore:
    store = MemoryVectorStore()
    old = tmp_path / "old"
    old.mkdir()
    write_chunks_atomic(old / "a.jsonl", [_chunk("a", 0), _chunk("a", 1)])
    index_chunks(old, store)
    return store


def test_replace_docs_removes_the_old_document_after_the_new_one_is_indexed(tmp_path: Path) -> None:
    store = _store_with_old_doc(tmp_path)
    new = tmp_path / "new"
    new.mkdir()
    write_chunks_atomic(new / "b.jsonl", [_chunk("b", 0)])
    result = index_chunks(new, store)
    assert replace_docs(store, ["DOC-aaaaaaaaaaaa"], keep=result.doc_ids) == {"DOC-aaaaaaaaaaaa": 2}
    assert {h.chunk.ref_id for h in _all(store)} == {"DOC-bbbbbbbbbbbb"}


def test_replace_docs_never_deletes_a_document_indexed_in_the_same_run(tmp_path: Path) -> None:
    store = _store_with_old_doc(tmp_path)
    result = index_chunks(tmp_path / "old", store)
    assert replace_docs(store, ["DOC-aaaaaaaaaaaa"], keep=result.doc_ids) == {"DOC-aaaaaaaaaaaa": 0}
    assert len(_all(store)) == 2


def test_cli_replace_doc_deletes_old_chunks_after_indexing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store_with_old_doc(tmp_path)
    new = tmp_path / "new"
    new.mkdir()
    write_chunks_atomic(new / "b.jsonl", [_chunk("b", 0)])
    monkeypatch.setattr(ingest_cli, "build_store", lambda settings: store)
    result = runner.invoke(app, ["ingest", "index", "--chunks", str(new), "--replace-doc", "DOC-aaaaaaaaaaaa"])
    assert result.exit_code == 0 and "DOC-aaaaaaaaaaaa" in result.output and "2 chunk cũ" in result.output
    assert {h.chunk.ref_id for h in _all(store)} == {"DOC-bbbbbbbbbbbb"}


def test_cli_replace_doc_keeps_old_chunks_when_a_file_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store_with_old_doc(tmp_path)
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "b.jsonl").write_text("not json\n")
    monkeypatch.setattr(ingest_cli, "build_store", lambda settings: store)
    result = runner.invoke(app, ["ingest", "index", "--chunks", str(bad), "--replace-doc", "DOC-aaaaaaaaaaaa"])
    assert result.exit_code == 1 and len(_all(store)) == 2


def test_cli_replace_doc_rejects_a_malformed_doc_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store_with_old_doc(tmp_path)
    monkeypatch.setattr(ingest_cli, "build_store", lambda settings: store)
    result = runner.invoke(app, ["ingest", "index", "--chunks", str(tmp_path / "old"), "--replace-doc", "oops"])
    assert result.exit_code == 2 and len(_all(store)) == 2
