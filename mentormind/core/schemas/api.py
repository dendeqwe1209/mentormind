"""REST API Request & Response Schemas (Spec 08)."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from mentormind.core.schemas.common import Citation, DataClassification
from mentormind.core.schemas.work_profile import (
    ErrorTag,
    ExceptionCase,
    Expert,
    ReasonSource,
    WorkProfile,
)


class ReviewAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


class ReviewRequest(BaseModel):
    action: ReviewAction
    reviewer: str = Field(min_length=1)
    comment: str | None = None
    error_tags: list[ErrorTag] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_reject_reason(self) -> ReviewRequest:
        if self.action == ReviewAction.REJECT and not (self.comment and self.comment.strip()):
            raise ValueError("Từ chối (reject) bắt buộc phải nhập lý do (comment).")
        return self


class ProfilePatchRequest(BaseModel):
    step: str | None = Field(default=None, min_length=3)
    hand_action: str | None = None
    objects: list[str] | None = None
    key_point: str | None = None
    reason: str | None = None
    reason_source: ReasonSource | None = None
    exceptions: list[ExceptionCase] | None = None
    pass_criteria: str | None = None
    equipment_id: str | None = None
    part_numbers: list[str] | None = None
    expert: Expert | None = None


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class JobResponse(BaseModel):
    job_id: str
    kind: str
    status: JobStatus
    result: Any | None = None
    error: str | None = None
    created_at: str | None = None
    finished_at: str | None = None


class DocumentIngestFile(BaseModel):
    """One uploaded file in the result of a ``POST /ingest/documents`` job (spec 08 §2)."""

    name: str
    doc_id: str | None = None
    extractor: str | None = None
    pages: int = 0
    chunks: int = 0
    #: Not a supported format (spec 02 FR-01); such a file has no ``error``.
    skipped: bool = False
    error: str | None = None


class DocumentIngestResult(BaseModel):
    """``JobResponse.result`` of a ``POST /ingest/documents`` job (spec 08 §2, AC-09)."""

    classification: DataClassification
    files: list[DocumentIngestFile] = Field(default_factory=list)
    chunks_indexed: int = 0


VideoStage = Literal["cut", "transcribe", "describe", "merge", "reasons"]


class VideoProcessProgress(BaseModel):
    """Where a video job is: its stage and how far into it (spec 08 §2).

    ``cut``: segments exported; ``transcribe``: seconds of audio heard; ``describe``: VLM calls of
    passes A and B; ``merge``: pass C (0/1); ``reasons``: steps with an excerpt sent to propose-reasons.
    """

    stage: VideoStage = "describe"
    done: float = Field(ge=0)
    total: float = Field(ge=0)


class VideoProcessResult(BaseModel):
    """``JobResponse.result`` of a ``POST /videos/{video_id}/process`` job (spec 08 §2, AC-14, AC-18)."""

    video_id: str
    process_id: str
    #: Cutting method asked for, and the one that ran (spec 03 FR-03 falls back when a library is missing).
    method: str = "fixed_window"
    method_used: str | None = None
    segments: int = 0
    #: ``profile_id`` of the drafts saved for this video, in step order.
    profiles: list[str] = Field(default_factory=list)
    failed_segments: list[str] = Field(default_factory=list)
    transcript_lines: int = 0
    #: Steps quoting at least one sentence of the expert (spec 04 §3).
    steps_with_excerpt: int = 0
    reasons_filled: int = 0
    progress: VideoProcessProgress | None = None


class ProfileDeleteRequest(BaseModel):
    """Body of ``POST /profiles/delete`` (spec 08 §2, AC-21)."""

    profile_ids: list[str] = Field(min_length=1)


class ProfileListItem(WorkProfile):
    """A ``GET /profiles`` item: the profile plus whether the knowledge graph serves it (spec 08 §2)."""

    #: In Neo4j + pgvector: deleting the step also unloads it (the UI warns). Not part of the contract.
    published: bool = False


class DeleteFailure(BaseModel):
    """A step kept because the graph / vector store could not drop it (spec 08 §2)."""

    profile_id: str
    error: str


class ProfileDeleteResult(BaseModel):
    """What a step deletion removed (spec 08 §2, AC-19..AC-21)."""

    #: Removed from the profile store.
    deleted: list[str] = Field(default_factory=list)
    #: Of ``deleted``: also removed from Neo4j and pgvector (they had been approved).
    unpublished: list[str] = Field(default_factory=list)
    #: Kept unchanged: published, and unloading them failed.
    failed: list[DeleteFailure] = Field(default_factory=list)


class VideoDeleteResult(ProfileDeleteResult):
    """``DELETE /videos/{video_id}`` (spec 08 §2, AC-22)."""

    video_id: str
    #: Files removed under ``data/work/video/<video_id>/`` and ``data/work/vlm/<video_id>/``.
    files_removed: int = 0


class DocumentInfo(BaseModel):
    """One indexed document of ``GET /documents``: a ``data/work/chunks/<doc_id>.jsonl`` (spec 08 §2, AC-23)."""

    doc_id: str
    #: File name of the source (from the chunks' ``source_path``).
    name: str
    title: str | None = None
    data_classification: DataClassification | None = None
    extractor: str | None = None
    chunks: int = 0


class DocumentDeleteResult(BaseModel):
    """``DELETE /documents/{doc_id}`` (spec 08 §2, AC-23)."""

    doc_id: str
    #: Chunks removed from the vector store.
    chunks_deleted: int = 0
    chunk_file_removed: bool = False
    #: Uploaded copies removed under ``data/work/docs/``.
    uploads_removed: int = 0


class AskRequest(BaseModel):
    process_id: str
    question: str
    top_k: int = 5


class AssistantAnswer(BaseModel):
    answer: str
    refused: bool = False
    suggested_expert: str | None = None
    citations: list[Citation] = Field(default_factory=list)


class RcaRequest(BaseModel):
    lot_id: str | None = None
    symptom: str | None = None


class Hypothesis(BaseModel):
    hypothesis: str
    likelihood: Literal["high", "medium", "low"]
    evidence_refs: list[str] = Field(default_factory=list)


class WhyStep(BaseModel):
    order: int
    question: str
    answer: str
    verified: bool


class RcaReport(BaseModel):
    lot_id: str | None = None
    symptom: str
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    five_whys: list[WhyStep] = Field(default_factory=list)
    related_lots: list[str] = Field(default_factory=list)
    preventive_actions: list[str] = Field(default_factory=list)
    disclaimer: str = "Kết quả phân tích dựa trên AI và dữ liệu mẫu, cần chuyên gia xác nhận trước khi áp dụng."


class LotRecord(BaseModel):
    lot_id: str
    process_id: str
    part_number: str
    produced_at: str
    defect_type: str | None = None
    status: str
