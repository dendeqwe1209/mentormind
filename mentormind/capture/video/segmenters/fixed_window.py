"""``fixed_window`` (spec 03 FR-03, the last fallback): windows of 10 s."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from mentormind.capture.video.segmenters.base import Cut
from mentormind.capture.video.segmenters.frames import FrameSource, sample_frames
from mentormind.capture.video.segmenters.motion import frame_motion, scored
from mentormind.core.schemas.video import VideoAsset

WINDOW_S = 10.0


def window_bounds(duration: float, window_s: float) -> list[tuple[float, float]]:
    """Consecutive ``window_s`` windows over ``duration`` (the tail may be shorter; FR-04 merges it)."""
    bounds: list[tuple[float, float]] = []
    start = 0.0
    while start < duration - 1e-6:
        end = min(start + window_s, duration)
        bounds.append((start, end))
        start = end
    return bounds


class FixedWindowSegmenter:
    name: Literal["fixed_window"] = "fixed_window"

    def __init__(self, window_s: float = WINDOW_S, *, motion: bool = True, frames: FrameSource = sample_frames) -> None:
        self.window_s = window_s
        #: False skips the frame-difference pass (``vlm sweep`` forces its own fps anyway).
        self.motion = motion
        self._frames = frames

    def cut(self, video: Path, asset: VideoAsset) -> list[Cut]:
        cuts = [Cut(start, end) for start, end in window_bounds(asset.duration_s, self.window_s)]
        return scored(cuts, frame_motion(video, frames=self._frames)) if self.motion else cuts
