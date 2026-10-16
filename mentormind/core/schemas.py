"""Pydantic schemas for MentorMind Know-How AI.

Conforms strictly to:
- docs/contracts/work_profile.schema.json (Contract v1.0)
- docs/08-api-and-ui.md (REST API & Profile Store spec)
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SchemaVersion(str, Enum):
    V1_0 = "1.0"


class GeneratedBy(str, Enum):
    VLM = "vlm"
    OCR = "ocr"
    HUMAN = "human"


class DataClassification(str, Enum):
    PUBLIC = "public"
    SYNTHETIC = "synthetic"
    FACTORY_CONFIDENTIAL = "factory_confidential"


class ProfileStatus(str, Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReasonSource(str, Enum):
    EXPERT_VERBAL = "expert_verbal"
    EXPERT_INTERVIEW = "expert_interview"


class ErrorTag(str, Enum):
    MISSED_STEP = "missed_step"
    HALLUCINATED_STEP = "hallucinated_step"
    WRONG_ORDER = "wrong_order"
    WRONG_OBJECT = "wrong_object"
    WRONG_ACTION = "wrong_action"
    OTHER = "other"


class ExceptionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case: str
    handling: str


class ExpertInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expert_id: str | None = None
    display_name: str | None = None


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    video_id: str | None = None
    t_start: float | None = Field(default=None, ge=0)
    t_end: float | None = Field(default=None, ge=0)
    segment_ids: list[str] = Field(default_factory=list)
    keyframes: list[str] = Field(default_factory=list)
    transcript_excerpt: str | None = None
    document_refs: list[str] = Field(default_factory=list)


class ModelInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str | None = None
    model: str | None = None
    fps: float | None = None


class ReviewInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviewer: str
    reviewed_at: str
    comment: str | None = None
    error_tags: list[ErrorTag] = Field(default_factory=list)


PROFILE_ID_REGEX = re.compile(r"^WP-[A-Z0-9]{3,}-[0-9]{3}$")


class WorkProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    profile_id: str
    process_id: str
    step_order: int = Field(ge=1)
    step: str = Field(min_length=3)
    hand_action: str | None = None
    objects: list[str] = Field(default_factory=list)
    key_point: str | None = None
    reason: str | None = None
    reason_source: ReasonSource | None = None
    exceptions: list[ExceptionItem] = Field(default_factory=list)
    pass_criteria: str | None = None
    equipment_id: str | None = None
    part_numbers: list[str] = Field(default_factory=list)
    expert: ExpertInfo | None = None
    evidence: Evidence
    confidence: float = Field(ge=0.0, le=1.0)
    generated_by: GeneratedBy
    model_info: ModelInfo | None = None
    data_classification: DataClassification
    status: ProfileStatus
    review: ReviewInfo | None = None
    created_at: str
    version: int = Field(default=1, ge=1)

    @field_validator("profile_id")
    @classmethod
    def validate_profile_id(cls, v: str) -> str:
        if not PROFILE_ID_REGEX.match(v):
            raise ValueError(f"profile_id '{v}' must match pattern ^WP-[A-Z0-9]{{3,}}-[0-9]{{3}}$")
        return v

    @model_validator(mode="after")
    def validate_constitution_and_contract_rules(self) -> WorkProfile:
        # Rule 1: Constitution Điều 3: Draft sinh bởi VLM tuyệt đối không được có reason
        if (
            self.generated_by == GeneratedBy.VLM
            and self.status == ProfileStatus.DRAFT
            and (self.reason is not None or self.reason_source is not None)
        ):
            raise ValueError("Constitution Điều 3: Bản nháp do VLM sinh không được có reason hoặc reason_source.")

        # Rule 2: Có reason thì bắt buộc phải có reason_source
        if self.reason and not self.reason_source:
            raise ValueError(
                "Bắt buộc phải chọn reason_source ('expert_verbal' hoặc 'expert_interview') khi có reason."
            )

        # Rule 3: Khi status là approved thì bắt buộc phải có review kèm reviewer và reviewed_at
        if self.status == ProfileStatus.APPROVED and (
            not self.review or not self.review.reviewer or not self.review.reviewed_at
        ):
            raise ValueError("Trạng thái 'approved' bắt buộc phải có thông tin review (reviewer và reviewed_at).")

        return self


# ==========================================
# REST API Request & Response Schemas
# ==========================================


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
    exceptions: list[ExceptionItem] | None = None
    pass_criteria: str | None = None
    equipment_id: str | None = None
    part_numbers: list[str] | None = None
    expert: ExpertInfo | None = None


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


class AskRequest(BaseModel):
    process_id: str
    question: str
    top_k: int = 5


class Citation(BaseModel):
    source_type: Literal["video", "document"]
    ref_id: str
    title: str | None = None
    t_start: float | None = None
    t_end: float | None = None
    excerpt: str | None = None
    keyframe_url: str | None = None


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
