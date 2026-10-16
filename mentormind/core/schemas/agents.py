"""Requests and answers of the two agents of spec 06 (Work Assistant §3, RCA Agent §4)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from mentormind.core.schemas.common import Citation

Likelihood = Literal["high", "medium", "low"]


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    process_id: str | None = None


class AssistantAnswer(BaseModel):
    #: Vietnamese, with markers [1], [2]...; marker [i+1] cites ``citations[i]``.
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    refused: bool
    #: ``display_name`` of the expert to ask when the assistant refuses.
    suggested_contact: str | None = None


class RcaRequest(BaseModel):
    lot_id: str | None = None
    symptom_text: str | None = None
    process_id: str | None = None

    @model_validator(mode="after")
    def _one_input(self) -> RcaRequest:
        if not (self.lot_id or self.symptom_text):
            raise ValueError("Cần lot_id hoặc symptom_text.")
        return self


class Hypothesis(BaseModel):
    cause: str
    likelihood: Likelihood
    evidence: list[Citation] = Field(default_factory=list)
    #: What to check on the floor to confirm the cause.
    check_actions: list[str] = Field(default_factory=list)


class WhyStep(BaseModel):
    why: str
    answer: str
    #: False = "cần xác minh tại hiện trường" (no evidence behind this answer).
    verified: bool


class RcaReport(BaseModel):
    lot_id: str | None
    symptom: str
    #: At most 3, sorted by likelihood.
    hypotheses: list[Hypothesis] = Field(max_length=3)
    #: 3 to 5 levels.
    five_why: list[WhyStep] = Field(min_length=3, max_length=5)
    related_lots: list[str] = Field(default_factory=list)
    #: ``profile_id`` of the steps that prevent the symptom.
    prevention_steps: list[str] = Field(default_factory=list)
    disclaimer: str = Field(min_length=1)
