"""Docling extractor: main path for pdf/docx/xlsx/pptx (spec 02 FR-02, proposal 5).

Docling runs OCR on image regions itself and exports tables as markdown. Its library is imported
on first use so the rest of ingest (and every unit test) works without the ``ingest`` extra.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path
from typing import Any

from mentormind.capture.ingest.extractors.base import ExtractorError
from mentormind.capture.ingest.raw import RawBlock, RawDocument
from mentormind.core.schemas import ChunkKind

SUFFIXES = (".pdf", ".docx", ".xlsx", ".pptx")
_SKIPPED = {"page_header", "page_footer", "chart"}
_SPACES = re.compile(r" {2,}")
_RULE_CELL = re.compile(r"-{3,}")
_RULE_ROW = re.compile(r"\s*\|[\s:|-]*-{3,}[\s:|-]*\s*")


class DoclingExtractor:
    name = "docling"

    def __init__(self) -> None:
        self._converter: Any = None

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in SUFFIXES

    def extract(self, path: Path) -> RawDocument:
        if self._converter is None:
            try:
                module = importlib.import_module("docling.document_converter")
            except ImportError as exc:
                raise ExtractorError("Thiếu docling: cài extra `ingest` (uv sync --extra ingest).") from exc
            self._converter = module.DocumentConverter()
        try:
            document = self._converter.convert(str(path)).document
        except Exception as exc:  # docling raises many unrelated types for bad input
            raise ExtractorError(f"Docling lỗi trên {path.name}: {exc}") from exc
        return docling_to_raw(document, path)


def docling_to_raw(document: Any, path: Path) -> RawDocument:
    """Map a Docling document to blocks; XLSX sheets arrive as pages 1..n."""
    blocks: list[RawBlock] = []
    heading: str | None = None
    title: str | None = None
    for item, _level in document.iterate_items():
        label = str(getattr(item.label, "value", item.label))
        if label in _SKIPPED:
            continue
        page = item.prov[0].page_no if getattr(item, "prov", None) else None
        if label == "picture":
            # OCR text found inside a drawing hangs off the picture and is not yielded by iterate_items.
            text, kind = _picture_text(item, document), ChunkKind.DRAWING_NOTE
        elif label == "table":
            text, kind = _compact_table(item.export_to_markdown(doc=document)), ChunkKind.TABLE
        else:
            text, kind = (getattr(item, "text", "") or "").strip(), ChunkKind.TEXT
            if label == "section_header":
                heading = text
                title = title or text
                text = f"{'#' * min(int(getattr(item, 'level', 1)) + 1, 6)} {text}"
            elif label == "list_item":
                text = f"- {text}"
            elif label == "caption":
                kind = ChunkKind.FIGURE_CAPTION
        if text.strip():
            blocks.append(RawBlock(kind=kind, text=text, page=page, heading=heading))
    return RawDocument(
        path=str(path), title=title, num_pages=int(document.num_pages()), blocks=blocks, extractor="docling"
    )


def _picture_text(picture: Any, document: Any) -> str:
    """Text lines OCR found inside a picture (label drawings, QR captions), one per line."""
    lines = [
        (getattr(child.resolve(document), "text", "") or "").strip()
        for child in getattr(picture, "children", None) or []
    ]
    return "\n".join(line for line in lines if line)


def _compact_table(markdown: str) -> str:
    """Drop Docling's column padding (it can be most of a wide table's tokens); rows/columns stay."""
    return "\n".join(_compact_line(line) for line in markdown.splitlines())


def _compact_line(line: str) -> str:
    if _RULE_ROW.fullmatch(line):
        cells = [_RULE_CELL.sub("---", cell.strip()) for cell in line.strip().strip("|").split("|")]
        return "| " + " | ".join(cells) + " |"
    return _SPACES.sub(" ", line).rstrip()
