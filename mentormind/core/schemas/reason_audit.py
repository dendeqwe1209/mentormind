"""One line of ``reasons_audit.jsonl``: what ``propose-reasons`` did with one profile (spec 04 §5).

The user's self-check of the reasons proposed from the expert's words: the LLM's yes/no and the
span it pointed at stay here, never in the WorkProfile (its contract is unchanged).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

ReasonDecision = Literal[
    "accepted",
    "rejected_not_verbatim",
    "rejected_junk",
    "no_reason",
    "unreadable",
    "rejected_contract",
]


class ReasonAuditRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str
    step: str
    transcript_excerpt: str
    #: The LLM's answer; ``None`` when it was not asked (junk excerpt) or its answer was unreadable.
    has_reason: bool | None = None
    purpose_span: str | None = None
    #: ``partial_ratio`` of ``purpose_span`` against the excerpt (0-100); ``None`` without a span.
    match_score: float | None = None
    junk: bool = False
    junk_why: str | None = None
    decision: ReasonDecision
    #: What was stored as the profile's ``reason`` (the expert's sentence), else ``None``.
    reason: str | None = None
    #: The LLM that was asked; ``None`` when none was.
    model: str | None = None
    timestamp: datetime
