"""Extractor-neutral view of a parsed document (spec 02b §5)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from mentormind.core.schemas import ChunkKind


class RawBlock(BaseModel):
    """One block as an extractor saw it; tables are markdown tables."""

    kind: ChunkKind
    text: str
    #: None when the source has no pages (e.g. an XLSX sheet without a number).
    page: int | None = None
    heading: str | None = None


class RawDocument(BaseModel):
    path: str
    title: str | None = None
    num_pages: int
    blocks: list[RawBlock]
    extractor: Literal["mmore", "docling", "surya"]
    metadata: dict[str, Any] = Field(default_factory=dict)
