"""spec 02 FR-02b — flag pages whose text layer is mis-encoded (DOC-01 style garbage)."""

from __future__ import annotations

from pathlib import Path

from mentormind.capture.ingest.pipeline import ingest_file
from mentormind.capture.ingest.quality import odd_ratio, suspect_pages
from mentormind.capture.ingest.raw import RawBlock, RawDocument
from mentormind.capture.ingest.tokens import WhitespaceTokenCounter
from mentormind.core.config import Settings
from mentormind.core.schemas import ChunkKind, DataClassification
from tests.capture.ingest.fakes import FakeExtractor

GARBAGE = "ʵʵ σϯιʔςΫχΧϧϨϏϡʔ ϛϡʔλϏδϣϯͱ ݈ݱ ݸ ʹ Ͱ ͷ ͱ ଞػछͷ ɹ ɹ " * 3
VIETNAMESE = "Quy trình thao tác chuẩn đóng gói linh kiện: kiểm tra lô, đặt vào khay và dán nhãn. " * 3
JAPANESE = "大量生産部品のリコールを防止するための極値統計による新しい品質管理法 " * 3
MATH = (
    "The supplier shall keep the process stable and record every change to the control plan. " * 3
    + "Resistance 4.7 kΩ ± 5% at 25 °C, Δt = 3 s, µ = 0.2."
)


def _doc(*pages: str) -> RawDocument:
    blocks = [RawBlock(kind=ChunkKind.TEXT, text=t, page=i) for i, t in enumerate(pages, start=1)]
    return RawDocument(path="x.pdf", num_pages=len(pages), extractor="docling", blocks=blocks)


def test_garbage_scores_high_and_real_text_scores_low() -> None:
    assert odd_ratio(GARBAGE) > 0.3
    for text in (VIETNAMESE, JAPANESE, MATH):
        assert odd_ratio(text) < 0.05, text[:20]


def test_only_the_broken_page_is_flagged() -> None:
    assert suspect_pages(_doc(VIETNAMESE, GARBAGE, JAPANESE), max_ratio=0.05) == [2]


def test_short_pages_are_never_flagged() -> None:
    assert suspect_pages(_doc("σϯι"), max_ratio=0.05) == []


def test_pages_none_blocks_are_ignored() -> None:
    raw = RawDocument(
        path="x", num_pages=1, extractor="docling", blocks=[RawBlock(kind=ChunkKind.TEXT, text=GARBAGE, page=None)]
    )
    assert suspect_pages(raw, max_ratio=0.05) == []


def test_pipeline_reports_suspect_pages_but_still_writes_chunks(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"x")
    result = ingest_file(
        src,
        DataClassification.PUBLIC,
        tmp_path / "out",
        extractors=[FakeExtractor("docling", doc=_doc(VIETNAMESE, GARBAGE))],
        counter=WhitespaceTokenCounter(),
        settings=Settings(_env_file=None),
    )
    assert not result.error and result.chunks > 0
    assert result.suspect_pages == [2]
