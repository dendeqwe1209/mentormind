"""Cutting methods of spec 03 FR-03, by name: ``hand_activity``, ``scene``, ``fixed_window``.

Each module imports its library (MediaPipe, PySceneDetect, OpenCV) only when it cuts; a method whose
library or model is missing raises ``SegmenterUnavailable`` and the next method of the chain runs.
"""

from mentormind.capture.video.segmenters.base import (
    FALLBACK,
    METHODS,
    Cut,
    Method,
    Segmenter,
    SegmenterUnavailable,
    cut_with_fallback,
)
from mentormind.capture.video.segmenters.fixed_window import WINDOW_S, FixedWindowSegmenter, window_bounds
from mentormind.capture.video.segmenters.hand_activity import HandActivitySegmenter
from mentormind.capture.video.segmenters.scene import SceneSegmenter
from mentormind.core.config import Settings


def build_segmenter(method: Method, settings: Settings, *, window_s: float = WINDOW_S) -> Segmenter:
    """The segmenter of ``method`` as configured (the hand model path comes from the settings)."""
    if method == "hand_activity":
        return HandActivitySegmenter(model=settings.video_hand_model)
    if method == "scene":
        return SceneSegmenter()
    return FixedWindowSegmenter(window_s)


__all__ = [
    "FALLBACK",
    "METHODS",
    "WINDOW_S",
    "Cut",
    "FixedWindowSegmenter",
    "HandActivitySegmenter",
    "Method",
    "SceneSegmenter",
    "Segmenter",
    "SegmenterUnavailable",
    "build_segmenter",
    "cut_with_fallback",
    "window_bounds",
]
