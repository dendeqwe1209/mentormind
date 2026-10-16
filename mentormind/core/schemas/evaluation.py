"""Evaluation inputs (spec 09): golden-set questions and the review events of spec 08 §1."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

QuestionType = Literal["how", "why", "exception", "relational", "out_of_scope"]
ReviewAction = Literal["approve", "reject"]
ErrorTagName = Literal["missed_step", "hallucinated_step", "wrong_order", "wrong_object", "wrong_action", "other"]


class GoldenQuestion(BaseModel):
    """One line of ``data/golden_set/qa.jsonl`` (spec 09 §2)."""

    model_config = ConfigDict(extra="forbid")

    qid: str = Field(pattern=r"^Q\d{3,}$")
    process_id: str
    type: QuestionType
    question: str = Field(min_length=3)
    #: What a right answer says; out-of-scope questions state that the assistant must refuse.
    ground_truth: str = Field(min_length=1)
    #: ``Citation.ref_id`` of any source type: ``WP-...``, ``DOC-...#...``, ``VID-...-Sxxx``,
    #: lot ids.
    expected_citations: list[str] = Field(default_factory=list)
    author: str
    created_at: date


class ReviewEvent(BaseModel):
    """A row of spec 08's ``review_events`` table."""

    id: int
    profile_id: str
    action: ReviewAction
    reviewer: str
    comment: str | None = None
    error_tags: list[ErrorTagName] = Field(default_factory=list)
    created_at: datetime
