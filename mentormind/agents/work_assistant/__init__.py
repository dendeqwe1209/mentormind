"""Work Assistant (spec 06 §3): a new worker asks about a step; a grounded answer or a refusal."""

from mentormind.agents.work_assistant.assistant import (
    ANSWER_SCHEMA,
    DEFAULT_MIN_COSINE,
    DEFAULT_MIN_SCORE,
    REFUSAL,
    WorkAssistant,
)

__all__ = ["ANSWER_SCHEMA", "DEFAULT_MIN_COSINE", "DEFAULT_MIN_SCORE", "REFUSAL", "WorkAssistant"]
