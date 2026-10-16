"""Docling adapter: document -> RawDocument (spec 02 FR-03; shapes from the T02-0 spike)."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any

import pytest

from mentormind.capture.ingest.extractors.base import ExtractorError
from mentormind.capture.ingest.extractors.docling import DoclingExtractor, docling_to_raw
from mentormind.core.schemas import ChunkKind

TABLE_MD = "| a | b |\n|---|---|\n| 1 | 2 |"


def item(label: str, text: str = "", page: int | None = 1, **extra: Any) -> NS:
    prov = [NS(page_no=page)] if page is not None else []
    return NS(label=NS(value=label), text=text, prov=prov, export_to_markdown=lambda doc=None: TABLE_MD, **extra)


def fake_doc(*items: NS, pages: int = 2) -> NS:
    return NS(iterate_items=lambda: [(i, 0) for i in items], num_pages=lambda: pages)


def test_blocks_map_to_kinds_and_pages() -> None:
    raw = docling_to_raw(
        fake_doc(
            item("section_header", "Đóng gói", level=1),
            item("text", "Đặt linh kiện."),
            item("list_item", "Kiểm tra lot", page=2),
            item("table", page=2),
            item("caption", "Hình 1: nhãn", page=2),
            item("picture", page=2),
            item("page_footer", "trang 1"),
        ),
        Path("a.pdf"),
    )
    assert [(b.kind, b.page) for b in raw.blocks] == [
        (ChunkKind.TEXT, 1),
        (ChunkKind.TEXT, 1),
        (ChunkKind.TEXT, 2),
        (ChunkKind.TABLE, 2),
        (ChunkKind.FIGURE_CAPTION, 2),
    ]
    assert raw.blocks[0].text == "## Đóng gói"
    assert raw.blocks[2].text == "- Kiểm tra lot"
    assert raw.blocks[3].text == "| a | b |\n| --- | --- |\n| 1 | 2 |"
    assert raw.extractor == "docling" and raw.num_pages == 2 and raw.title == "Đóng gói"


def test_heading_is_tracked_for_following_blocks() -> None:
    raw = docling_to_raw(fake_doc(item("section_header", "A", level=1), item("text", "x")), Path("a.pdf"))
    assert raw.blocks[1].heading == "A"


def test_item_without_page_has_page_none() -> None:
    raw = docling_to_raw(fake_doc(item("text", "x", page=None)), Path("a.pdf"))
    assert raw.blocks[0].page is None


def test_blank_text_items_are_dropped() -> None:
    assert docling_to_raw(fake_doc(item("text", "  ")), Path("a.pdf")).blocks == []


def test_missing_library_gives_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(name: str) -> Any:
        raise ImportError(name)

    monkeypatch.setattr(importlib, "import_module", boom)
    with pytest.raises(ExtractorError, match="extra `ingest`"):
        DoclingExtractor().extract(Path("a.pdf"))


def test_supports_office_formats_case_insensitively() -> None:
    ex = DoclingExtractor()
    assert all(ex.supports(Path(f"a{s}")) for s in (".pdf", ".DOCX", ".xlsx", ".pptx"))
    assert not ex.supports(Path("a.txt"))


def test_table_padding_is_compacted_without_losing_rows_or_columns() -> None:
    padded = "| Mã     |   Tên       |\n|--------|-------------|\n| A1     | linh   kiện |"
    table = item("table")
    table.export_to_markdown = lambda doc=None: padded
    [block] = docling_to_raw(fake_doc(table), Path("a.pdf")).blocks
    assert block.text == "| Mã | Tên |\n| --- | --- |\n| A1 | linh kiện |"


def test_ac_03_text_inside_a_picture_becomes_a_drawing_note() -> None:
    # DOC-04 p.3: a container-label drawing whose text Docling's OCR attaches as children of the picture.
    kids = [NS(text="Part No. (P)"), NS(text="TN057763-7131"), NS(text="  ")]
    picture = item("picture", page=3, children=[NS(resolve=lambda doc, k=k: k) for k in kids])
    [block] = docling_to_raw(fake_doc(picture), Path("a.pdf")).blocks
    assert (block.kind, block.page) == (ChunkKind.DRAWING_NOTE, 3)
    assert block.text == "Part No. (P)\nTN057763-7131"


def test_picture_without_ocr_text_adds_no_block() -> None:
    assert docling_to_raw(fake_doc(item("picture", children=[])), Path("a.pdf")).blocks == []
