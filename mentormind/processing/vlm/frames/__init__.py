"""Preparing frames for a VLM call: adaptive-fps sampling, resize, near-duplicate removal."""

from mentormind.processing.vlm.frames.dedup import DUPLICATE_MAX_HAMMING, dhash, hamming
from mentormind.processing.vlm.frames.sampler import (
    LONG_SIDE_PX,
    SampledFrames,
    choose_fps,
    sample_frames,
)

__all__ = [
    "DUPLICATE_MAX_HAMMING",
    "LONG_SIDE_PX",
    "SampledFrames",
    "choose_fps",
    "dhash",
    "hamming",
    "sample_frames",
]
