"""Data exchanged with an ASR provider: timed words and stretches of speech (spec 03 FR-07c)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ASRWord(BaseModel):
    """One recognised word with its time in the audio (seconds)."""

    model_config = ConfigDict(frozen=True)

    text: str
    t_start: float = Field(ge=0)
    t_end: float = Field(ge=0)
    probability: float | None = Field(default=None, ge=0, le=1)


class ASRSegment(BaseModel):
    """One stretch of speech as the engine returns it (for Whisper: one decoding window)."""

    model_config = ConfigDict(frozen=True)

    text: str
    t_start: float = Field(ge=0)
    t_end: float = Field(ge=0)
    #: Word timestamps; empty when the engine gave none (then the stretch is cut as one sentence).
    words: tuple[ASRWord, ...] = ()


class ASRResult(BaseModel):
    """Everything one ``transcribe`` call heard, with what it cost."""

    model_config = ConfigDict(frozen=True)

    segments: tuple[ASRSegment, ...]
    #: Language used or detected (ISO 639-1, e.g. "vi").
    language: str
    #: Length of the audio, seconds.
    duration_s: float = Field(ge=0)
    latency_s: float = Field(ge=0)
    provider: str
    model: str
