"""Rows of the vector table ``KNOWHOW_VECTOR_TABLE`` (spec 01 FR-05c, spec 02 FR-07, spec 05 FR-06).

One table holds document chunks and approved work_profile chunks side by side; ``source_type``
tells them apart and ``chunk_id`` is the upsert key, so indexing twice never duplicates.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from mentormind.core.schemas.common import DataClassification

SourceType = Literal["work_profile", "document", "video_segment", "sigma"]


class VectorChunk(BaseModel):
    """One searchable passage; columns mirror ``public.knowhow_chunks`` in ``init.sql``."""

    chunk_id: str
    source_type: SourceType
    #: ``Citation.ref_id`` (spec 05): profile_id, doc_id, segment_id...
    ref_id: str
    text: str = Field(min_length=1)
    #: spec 02 ``ChunkKind`` for documents; None otherwise.
    kind: str | None = None
    process_ids: list[str] = Field(default_factory=list)
    part_numbers: list[str] = Field(default_factory=list)
    data_classification: DataClassification
    metadata: dict[str, Any] = Field(default_factory=dict)
    #: Filled by the store from its embedder when missing.
    embedding: list[float] | None = Field(default=None, repr=False)


class VectorHit(BaseModel):
    """One search result: the chunk and its fused (RRF) score, higher is better."""

    chunk: VectorChunk
    score: float
