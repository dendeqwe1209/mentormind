"""Types shared by every schema (spec 01 §2, spec 05 §4)."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel


class DataClassification(StrEnum):
    """Sensitivity label carried by every data source (constitution art. 2)."""

    PUBLIC = "public"
    SYNTHETIC = "synthetic"
    FACTORY_CONFIDENTIAL = "factory_confidential"


class Citation(BaseModel):
    """Evidence an agent answer points to (spec 05 §4, spec 08)."""

    source_type: Literal["work_profile", "document", "video_segment", "sigma", "video"]
    ref_id: str
    snippet: str = ""
    title: str | None = None
    t_start: float | None = None
    t_end: float | None = None
    excerpt: str | None = None
    keyframe_url: str | None = None
    score: float | None = None
