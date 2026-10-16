"""Video data model (spec 03 §3): assets, segments and transcript lines."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from mentormind.core.schemas.common import DataClassification


class VideoAsset(BaseModel):
    video_id: str  # "VID-" + sha256[:12]
    path: str
    duration_s: float
    fps: float
    has_audio: bool
    process_id: str | None
    data_classification: DataClassification


class Segment(BaseModel):
    segment_id: str  # f"{video_id}-S{index:03d}"
    video_id: str
    index: int
    t_start: float
    t_end: float
    method: Literal["scene", "hand_activity", "fixed_window"]
    motion_score: float | None  # 0..1, None when not computed
    keyframes: list[str]  # JPG paths
    clip_path: str  # cut mp4
    # Inherited from VideoAsset so DataGuard (spec 04) can check without a lookup.
    data_classification: DataClassification


class TranscriptSegment(BaseModel):
    video_id: str
    t_start: float
    t_end: float
    text: str
    language: str
    source: Literal["inline", "cued_recall"] = "inline"
    data_classification: DataClassification
