"""Data exchanged with a VLM provider: frames going in, the raw answer coming out."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from mentormind.core.providers.models import TokenUsage


class ImageInput(BaseModel):
    """One frame, already read from disk."""

    model_config = ConfigDict(frozen=True)

    path: Path
    mime_type: Literal["image/jpeg", "image/png"]
    data: bytes = Field(repr=False)


class VLMResponse(BaseModel):
    """Raw answer of one call; kept whole so the pipeline can store it for debugging (FR-06)."""

    model_config = ConfigDict(frozen=True)

    text: str
    usage: TokenUsage | None
    latency_s: float = Field(ge=0)
    provider: str
    model: str
