"""Chunks produced by document ingest (spec 02 §3, 02b §4.1)."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from mentormind.core.schemas.common import DataClassification

CHUNK_ID_PATTERN = re.compile(r"^DOC-[0-9a-f]{12}#p\d+-\d+$")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$", re.M)


class ChunkKind(StrEnum):
    TEXT = "text"
    TABLE = "table"
    FIGURE_CAPTION = "figure_caption"
    DRAWING_NOTE = "drawing_note"


class DocumentChunk(BaseModel):
    """One passage of an ingested document; one JSONL line per chunk."""

    #: ``f"{doc_id}#p{page}-{index}"``; ``page`` is the sheet/section number for XLSX/DOCX.
    chunk_id: str
    #: Matches ``Citation.source_type`` (spec 05); used as a filter column in the vector table.
    source_type: Literal["document"] = "document"
    #: ``"DOC-" + sha256(file bytes)[:12]``.
    doc_id: str
    source_path: str
    title: str | None = None
    page: int | None = None
    kind: ChunkKind
    #: Markdown; tables stay markdown tables.
    text: str
    process_ids: list[str] = Field(default_factory=list)
    part_numbers: list[str] = Field(default_factory=list)
    data_classification: DataClassification
    extractor: Literal["mmore", "docling", "surya"]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("chunk_id")
    @classmethod
    def _check_chunk_id(cls, value: str) -> str:
        if not CHUNK_ID_PATTERN.match(value):
            raise ValueError(f"chunk_id must match {CHUNK_ID_PATTERN.pattern}: {value!r}")
        return value

    @field_validator("text")
    @classmethod
    def _check_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be empty")
        return value

    @field_validator("process_ids", "part_numbers")
    @classmethod
    def _dedupe_sorted(cls, value: list[str]) -> list[str]:
        return sorted(set(value))

    @model_validator(mode="after")
    def _check_table(self) -> DocumentChunk:
        if self.kind is ChunkKind.TABLE and not _TABLE_SEPARATOR.search(self.text):
            raise ValueError("kind=table requires a markdown table (separator row of ---)")
        return self
