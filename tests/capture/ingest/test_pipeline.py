"""spec 02 FR-01/06/08, AC-04, AC-05, AC-09 — ingest_file / ingest_path."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from mentormind.capture.ingest.extractors.base import ExtractorError
from mentormind.capture.ingest.jsonl import read_chunks
from mentormind.capture.ingest.pipeline import doc_id_for, ingest_file, ingest_path
from mentormind.capture.ingest.raw import RawBlock, RawDocument
from mentormind.capture.ingest.tokens import WhitespaceTokenCounter
from mentormind.core.config import Settings
from mentormind.core.guard.data_guard import ConfidentialDataError
from mentormind.core.schemas import ChunkKind, DataClassification
from tests.capture.ingest.fakes import FakeExtractor

SETTINGS = Settings(_env_file=None)
COUNTER = WhitespaceTokenCounter()
OFFICE = (".pdf", ".docx", ".xlsx", ".pptx")


def _doc() -> RawDocument:
    return RawDocument(
        path="x",
        num_pages=2,
        extractor="docling",
        blocks=[
            RawBlock(kind=ChunkKind.TEXT, text="Công đoạn PACK01.", page=1),
            RawBlock(kind=ChunkKind.TABLE, text="| a | b |\n| --- | --- |\n| 1 | 2 |", page=2),
        ],
    )


def _run(tmp_path: Path, name: str = "a.pdf", content: bytes = b"hello", **kw: object):
    src = tmp_path / name
    src.write_bytes(content)
    params: dict[str, object] = {
        "extractors": [FakeExtractor("docling", suffixes=OFFICE, doc=_doc())],
        "counter": COUNTER,
        "settings": SETTINGS,
    }
    params.update(kw)
    return ingest_file(src, DataClassification.PUBLIC, tmp_path / "out", **params)  # type: ignore[arg-type]


def test_doc_id_is_sha256_prefix_of_bytes(tmp_path: Path) -> None:
    f = tmp_path / "a.pdf"
    f.write_bytes(b"abc")
    assert doc_id_for(f) == "DOC-" + hashlib.sha256(b"abc").hexdigest()[:12]


def test_ac_04_run_twice_same_lines_and_ids(tmp_path: Path) -> None:
    first = _run(tmp_path)
    out = tmp_path / "out" / f"{first.doc_id}.jsonl"
    before = out.read_bytes()
    second = _run(tmp_path)
    assert second.error is None and out.read_bytes() == before
    assert [c.chunk_id for _, c in read_chunks(out)] == [f"{first.doc_id}#p1-0", f"{first.doc_id}#p2-0"]


def test_ac_05_classification_written_to_every_chunk(tmp_path: Path) -> None:
    result = ingest_file(
        _src(tmp_path),
        DataClassification.SYNTHETIC,
        tmp_path / "out",
        extractors=[FakeExtractor("docling", doc=_doc())],
        counter=COUNTER,
        settings=SETTINGS,
    )
    labels = {c.data_classification for _, c in read_chunks(tmp_path / "out" / f"{result.doc_id}.jsonl")}
    assert labels == {DataClassification.SYNTHETIC}


def _src(tmp_path: Path) -> Path:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"hello")
    return src


def test_ac_09_reingest_with_other_label_errors_and_keeps_file(tmp_path: Path) -> None:
    ok = _run(tmp_path)
    out = tmp_path / "out" / f"{ok.doc_id}.jsonl"
    before = out.read_bytes()
    result = ingest_file(
        _src(tmp_path),
        DataClassification.FACTORY_CONFIDENTIAL,
        tmp_path / "out",
        extractors=[FakeExtractor("docling", doc=_doc())],
        counter=COUNTER,
        settings=SETTINGS,
    )
    assert result.error and "--force" in result.error
    assert out.read_bytes() == before


def test_ac_09_force_overwrites(tmp_path: Path) -> None:
    ok = _run(tmp_path)
    result = ingest_file(
        _src(tmp_path),
        DataClassification.FACTORY_CONFIDENTIAL,
        tmp_path / "out",
        extractors=[FakeExtractor("docling", doc=_doc())],
        counter=COUNTER,
        settings=SETTINGS,
        force=True,
    )
    assert result.error is None
    labels = {c.data_classification for _, c in read_chunks(tmp_path / "out" / f"{ok.doc_id}.jsonl")}
    assert labels == {DataClassification.FACTORY_CONFIDENTIAL}


def test_unsupported_extension_skipped(tmp_path: Path) -> None:
    result = _run(tmp_path, name="notes.txt")
    assert result.skipped and result.error is None and not (tmp_path / "out").exists()


def test_extractor_failure_is_reported_not_raised(tmp_path: Path) -> None:
    result = _run(tmp_path, extractors=[FakeExtractor("docling", raises=ExtractorError("boom"))])
    assert result.error and "boom" in result.error and not (tmp_path / "out").exists()


def test_invalid_chunk_is_reported_for_that_file_not_raised(tmp_path: Path) -> None:
    # A table block with no separator row cannot become a DocumentChunk; the batch must go on.
    bad = RawDocument(
        path="x", num_pages=1, extractor="docling", blocks=[RawBlock(kind=ChunkKind.TABLE, text="not a table", page=1)]
    )
    result = _run(tmp_path, extractors=[FakeExtractor("docling", doc=bad)])
    assert result.error and "markdown table" in result.error and not (tmp_path / "out").exists()


def test_fallback_reasons_and_extractor_are_reported(tmp_path: Path) -> None:
    chain = [
        FakeExtractor("docling", raises=ExtractorError("boom")),
        FakeExtractor("mmore", doc=_doc().model_copy(update={"extractor": "mmore"})),
    ]
    result = _run(tmp_path, extractors=chain)
    assert result.extractor == "mmore" and result.reasons and result.chunks == 2 and result.pages == 2


def test_ingest_path_walks_directory_and_continues_after_failure(tmp_path: Path) -> None:
    src = tmp_path / "in"
    (src / "sub").mkdir(parents=True)
    (src / "a.pdf").write_bytes(b"1")
    (src / "sub" / "b.pdf").write_bytes(b"2")
    (src / "c.txt").write_bytes(b"3")
    calls = {"n": 0}

    class Flaky(FakeExtractor):
        def extract(self, path: Path) -> RawDocument:
            calls["n"] += 1
            if path.name == "a.pdf":
                raise ExtractorError("bad a")
            return super().extract(path)

    results = ingest_path(
        src,
        DataClassification.PUBLIC,
        tmp_path / "out",
        extractors=[Flaky("docling", doc=_doc())],
        counter=COUNTER,
        settings=SETTINGS,
    )
    by_name = {Path(r.path).name: r for r in results}
    assert by_name["a.pdf"].error and by_name["b.pdf"].chunks == 2 and by_name["c.txt"].skipped
    assert calls["n"] == 2


def test_ingest_path_single_file(tmp_path: Path) -> None:
    results = ingest_path(
        _src(tmp_path),
        DataClassification.PUBLIC,
        tmp_path / "out",
        extractors=[FakeExtractor("docling", doc=_doc())],
        counter=COUNTER,
        settings=SETTINGS,
    )
    assert len(results) == 1 and results[0].chunks == 2


def test_missing_input_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ingest_path(
            tmp_path / "nope",
            DataClassification.PUBLIC,
            tmp_path / "out",
            extractors=[],
            counter=COUNTER,
            settings=SETTINGS,
        )


def test_data_guard_is_consulted_once_with_a_local_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[object, bool]] = []
    from mentormind.capture.ingest import pipeline

    monkeypatch.setattr(pipeline.DataGuard, "check", lambda c, p: seen.append((c, p.is_cloud)))
    src = tmp_path / "in"
    src.mkdir()
    (src / "a.pdf").write_bytes(b"1")
    (src / "b.pdf").write_bytes(b"2")
    ingest_path(
        src,
        DataClassification.PUBLIC,
        tmp_path / "out",
        extractors=[FakeExtractor("docling", doc=_doc())],
        counter=COUNTER,
        settings=SETTINGS,
    )
    assert seen == [(DataClassification.PUBLIC, False)]


def test_data_guard_refusal_propagates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mentormind.capture.ingest import pipeline

    def refuse(c: object, p: object) -> None:
        raise ConfidentialDataError("no")

    monkeypatch.setattr(pipeline.DataGuard, "check", refuse)
    with pytest.raises(ConfidentialDataError):
        ingest_path(
            _src(tmp_path),
            DataClassification.PUBLIC,
            tmp_path / "out",
            extractors=[],
            counter=COUNTER,
            settings=SETTINGS,
        )
