"""spec 02 FR-06 — atomic, deterministic JSONL I/O."""

from __future__ import annotations

from pathlib import Path

import pytest

from mentormind.capture.ingest.jsonl import ChunkFileError, read_chunks, write_chunks_atomic
from mentormind.core.schemas import ChunkKind, DataClassification, DocumentChunk


def _chunk(i: int) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=f"DOC-0123456789ab#p1-{i}",
        doc_id="DOC-0123456789ab",
        source_path="x.pdf",
        page=1,
        kind=ChunkKind.TEXT,
        text=f"đoạn {i}",
        data_classification=DataClassification.PUBLIC,
        extractor="docling",
    )


def test_roundtrip_and_one_line_per_chunk(tmp_path: Path) -> None:
    out = tmp_path / "d.jsonl"
    write_chunks_atomic(out, [_chunk(0), _chunk(1)])
    assert len(out.read_text().splitlines()) == 2
    assert [c for _, c in read_chunks(out)] == [_chunk(0), _chunk(1)]


def test_bytes_identical_on_rewrite(tmp_path: Path) -> None:
    out = tmp_path / "d.jsonl"
    write_chunks_atomic(out, [_chunk(0)])
    first = out.read_bytes()
    write_chunks_atomic(out, [_chunk(0)])
    assert out.read_bytes() == first


def test_failure_midway_leaves_no_partial_file(tmp_path: Path) -> None:
    out = tmp_path / "d.jsonl"

    def broken() -> object:
        yield _chunk(0)
        raise RuntimeError("disk full")

    with pytest.raises(RuntimeError):
        write_chunks_atomic(out, broken())  # type: ignore[arg-type]
    assert list(tmp_path.iterdir()) == []


def test_failure_keeps_previous_good_file(tmp_path: Path) -> None:
    out = tmp_path / "d.jsonl"
    write_chunks_atomic(out, [_chunk(0)])
    before = out.read_bytes()

    def broken() -> object:
        raise RuntimeError("boom")
        yield  # pragma: no cover

    with pytest.raises(RuntimeError):
        write_chunks_atomic(out, broken())  # type: ignore[arg-type]
    assert out.read_bytes() == before


def test_bad_line_reports_file_and_line(tmp_path: Path) -> None:
    out = tmp_path / "d.jsonl"
    write_chunks_atomic(out, [_chunk(0)])
    out.write_text(out.read_text() + '{"chunk_id": "nope"}\n')
    with pytest.raises(ChunkFileError, match=r"d\.jsonl.*dòng 2"):
        list(read_chunks(out))
