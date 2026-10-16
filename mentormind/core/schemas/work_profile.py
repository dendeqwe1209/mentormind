"""WorkProfile — Pydantic twin of ``docs/contracts/work_profile.schema.json`` (spec 01 FR-08).

The JSON Schema contract is the source of truth; this model mirrors it field for field so code
gets typed access, and :func:`validate_against_contract` re-checks any dumped profile against the
contract itself so the two can never silently drift apart.

Fields the contract declares optional but NOT nullable (``expert.expert_id``, ``review.reviewer``,
``model_info.*``...) are ``X | None = None`` here and dropped from the dump when unset, because
emitting ``null`` for them would violate the contract.
"""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from mentormind.core.schemas.common import DataClassification

CONTRACT_PATH = Path(__file__).resolve().parents[3] / "docs" / "contracts" / "work_profile.schema.json"
SCHEMA_VERSION: Literal["1.0"] = "1.0"

GeneratedBy = Literal["vlm", "ocr", "human"]
#: Who performs the step: a person (worker or engineer), an arm robot, or a fixed machine.
Actor = Literal["human", "robot", "machine"]
ProfileStatus = Literal["draft", "in_review", "approved", "rejected"]
ReasonSource = Literal["expert_verbal", "expert_interview"]
ErrorTag = Literal["missed_step", "hallucinated_step", "wrong_order", "wrong_object", "wrong_action", "other"]


class ContractValidationError(ValueError):
    """A document does not satisfy ``work_profile.schema.json``."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("WorkProfile vi phạm contract: " + "; ".join(errors))
        self.errors = errors


class _DropUnsetOptional(BaseModel):
    """Omit ``None`` values of optional-but-not-nullable fields from the dump."""

    _non_nullable: frozenset[str] = frozenset()

    @model_serializer(mode="wrap")
    def _drop_none(self, handler: SerializerFunctionWrapHandler, info: SerializationInfo) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        return {k: v for k, v in data.items() if not (k in self._non_nullable and v is None)}


class ExceptionCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case: str
    handling: str


class Expert(_DropUnsetOptional):
    model_config = ConfigDict(extra="forbid")
    _non_nullable = frozenset({"expert_id", "display_name"})

    expert_id: str | None = None
    display_name: str | None = None


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    video_id: str | None
    t_start: float | None = Field(default=None, ge=0)
    t_end: float | None = Field(default=None, ge=0)
    segment_ids: list[str] = Field(default_factory=list)
    keyframes: list[str] = Field(default_factory=list)
    transcript_excerpt: str | None = None
    document_refs: list[str] = Field(default_factory=list)


class ModelInfo(_DropUnsetOptional):
    # The contract leaves ``additionalProperties`` open for model_info.
    model_config = ConfigDict(extra="allow")
    _non_nullable = frozenset({"provider", "model", "fps"})

    provider: str | None = None
    model: str | None = None
    fps: float | None = None


class Review(_DropUnsetOptional):
    model_config = ConfigDict(extra="forbid")
    _non_nullable = frozenset({"reviewer", "reviewed_at"})

    reviewer: str | None = None
    reviewed_at: datetime | None = None
    comment: str | None = None
    error_tags: list[ErrorTag] = Field(default_factory=list)


class WorkProfile(BaseModel):
    """One observed work step plus the expert know-how behind it (contract v1.0)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    profile_id: str = Field(pattern=r"^WP-[A-Z0-9]{3,}-[0-9]{3}$")
    process_id: str
    step_order: int = Field(ge=1)
    step: str = Field(min_length=3)
    #: ``None`` = could not tell who performs the step.
    actor: Actor | None = None
    hand_action: str | None = None
    objects: list[str] = Field(default_factory=list)
    key_point: str | None = None
    reason: str | None = None
    reason_source: ReasonSource | None = None
    exceptions: list[ExceptionCase] = Field(default_factory=list)
    pass_criteria: str | None = None
    equipment_id: str | None = None
    part_numbers: list[str] = Field(default_factory=list)
    expert: Expert | None = None
    evidence: Evidence
    confidence: float = Field(ge=0, le=1)
    generated_by: GeneratedBy
    model_info: ModelInfo | None = None
    data_classification: DataClassification
    status: ProfileStatus
    review: Review | None = None
    created_at: datetime
    version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def _check_contract_rules(self) -> WorkProfile:
        # Contract allOf[0] — constitution art. 3: a VLM draft never carries a reason.
        is_vlm_draft = self.generated_by == "vlm" and self.status == "draft"
        if is_vlm_draft and (self.reason is not None or self.reason_source is not None):
            raise ValueError("Constitution Điều 3: Bản nháp do VLM sinh không được có reason hoặc reason_source.")
        # Contract allOf[1]: a reason must say which expert channel it came from.
        if self.reason is not None and self.reason_source is None:
            raise ValueError(
                "Bắt buộc phải chọn reason_source hợp lệ ('expert_verbal' hoặc 'expert_interview') khi có reason."
            )
        # Contract allOf[2]: approval must be attributable.
        if self.status == "approved" and (
            self.review is None or self.review.reviewer is None or self.review.reviewed_at is None
        ):
            raise ValueError("Profile approved phải có review.reviewer và review.reviewed_at.")
        return self

    def to_contract_dict(self) -> dict[str, Any]:
        """Dump in the exact shape the contract validates (JSON types, ISO datetimes)."""
        return self.model_dump(mode="json")


@lru_cache(maxsize=1)
def _contract_validator() -> Draft202012Validator:
    schema = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_against_contract(obj: WorkProfile | dict[str, Any]) -> None:
    """Raise :class:`ContractValidationError` unless ``obj`` satisfies the JSON contract."""
    document = obj.to_contract_dict() if isinstance(obj, WorkProfile) else obj
    errors = sorted(_contract_validator().iter_errors(document), key=lambda e: list(e.absolute_path))
    if errors:
        raise ContractValidationError(
            [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in errors]
        )
