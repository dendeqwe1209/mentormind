"""Data models of pass A: the step as the VLM reports it, placed on the timeline, the run."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from mentormind.core.schemas.work_profile import Actor

#: Words a model (or an annotator) uses for each actor, checked in this order: "người vận hành
#: máy" is a person, "máy robot" is a robot.
_ACTOR_WORDS: tuple[tuple[Actor, tuple[str, ...]], ...] = (
    ("robot", ("robot", "scara", "cobot")),
    (
        "human",
        ("human", "worker", "engineer", "operator", "technician", "person", "người", "nhân",
         "kỹ sư", "kỹ thuật", "chuyên gia", "thợ"),
    ),
    ("machine", ("machine", "máy", "băng tải", "băng chuyền", "conveyor")),
)  # fmt: skip


def normalize_actor(value: Any) -> Actor | None:
    """``human`` / ``robot`` / ``machine`` from the model's wording; ``None`` when unclear."""
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    for actor, words in _ACTOR_WORDS:
        if any(word in text for word in words):
            return actor
    return None


class ObservedStep(BaseModel):
    """One step exactly as the VLM reported it (relative times). Unknown keys are dropped."""

    model_config = ConfigDict(extra="ignore")

    step: str = Field(min_length=3)
    actor: Actor | None = None
    hand_action: str | None = None
    objects: list[str] = Field(default_factory=list)
    key_point_observed: str | None = None
    t_start_rel: float = Field(ge=0)
    t_end_rel: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)

    @field_validator("objects", mode="before")
    @classmethod
    def _objects_as_list(cls, value: Any) -> Any:
        # json_object endpoints (DashScope) do not enforce the schema: "cốc, thùng" means a list.
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return [] if value is None else value

    @field_validator("actor", mode="before")
    @classmethod
    def _actor_from_words(cls, value: Any) -> Actor | None:
        # An unexpected word ("công nhân", "robot SCARA") must not fail the whole segment.
        return normalize_actor(value)


class PassAOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    #: One or two sentences on what the frames show, written before the steps.
    scene: str | None = None
    steps: list[ObservedStep]


class TimedStep(BaseModel):
    """A pass-A step placed on the video timeline (absolute seconds)."""

    segment_id: str
    t_start: float = Field(ge=0)
    t_end: float = Field(ge=0)
    step: str
    actor: Actor | None = None
    hand_action: str | None = None
    objects: list[str] = Field(default_factory=list)
    key_point_observed: str | None = None
    confidence: float = Field(ge=0, le=1)
    fps: float = Field(gt=0)
    keyframes: list[str] = Field(default_factory=list)
    #: Every segment the step spans once pass C merged it across a boundary; empty = ``segment_id``.
    segment_ids: list[str] = Field(default_factory=list)

    def sources(self) -> list[str]:
        """Segments this step was observed in, in time order."""
        return self.segment_ids or [self.segment_id]


class FailedSegment(BaseModel):
    segment_id: str
    error: str
    raw_text: str


class PassAResult(BaseModel):
    steps: list[TimedStep] = Field(default_factory=list)
    failed: list[FailedSegment] = Field(default_factory=list)
    #: segment_id -> the model's own description of the segment ("scene").
    scenes: dict[str, str] = Field(default_factory=dict)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0
    calls: int = 0

    @property
    def tokens_used(self) -> int:
        return self.prompt_tokens + self.completion_tokens
