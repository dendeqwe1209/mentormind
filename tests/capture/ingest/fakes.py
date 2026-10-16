"""Test doubles for the extractor interface (constitution art. 6: no real tools in unit tests)."""

from __future__ import annotations

from pathlib import Path

from mentormind.capture.ingest.raw import RawBlock, RawDocument
from mentormind.core.schemas import ChunkKind


def raw_doc(extractor: str = "docling", blocks: int = 1) -> RawDocument:
    return RawDocument(
        path="x.pdf",
        num_pages=1,
        extractor=extractor,
        blocks=[RawBlock(kind=ChunkKind.TEXT, text=f"block {i}", page=1) for i in range(blocks)],
    )


class FakeExtractor:
    def __init__(
        self,
        name: str,
        *,
        suffixes: tuple[str, ...] = (".pdf",),
        doc: RawDocument | None = None,
        raises: Exception | None = None,
    ) -> None:
        self.name = name
        self._suffixes = suffixes
        self._doc = doc if doc is not None else raw_doc(name)
        self._raises = raises
        self.calls = 0

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in self._suffixes

    def extract(self, path: Path) -> RawDocument:
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        return self._doc
