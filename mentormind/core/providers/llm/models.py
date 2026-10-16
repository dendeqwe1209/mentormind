"""Data exchanged with an LLM provider."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from mentormind.core.providers.models import TokenUsage


class LLMResponse(BaseModel):
    """Raw answer of one call, with what it cost."""

    model_config = ConfigDict(frozen=True)

    text: str
    usage: TokenUsage | None
    latency_s: float = Field(ge=0)
    provider: str
    model: str
