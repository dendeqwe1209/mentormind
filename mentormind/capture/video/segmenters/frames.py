"""Small frames of a video at a low rate, read as a stream (one frame in memory at a time)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

#: ``(video, fps, long_side) -> (seconds, BGR frame)`` in time order.
FrameSource = Callable[[Path, float, int], Iterator[tuple[float, Any]]]


def sample_frames(video: Path, fps: float, long_side: int) -> Iterator[tuple[float, Any]]:
    """Every ``1/fps`` s of ``video``, downscaled so the long side is at most ``long_side`` px."""
    import cv2

    capture = cv2.VideoCapture(str(video))
    try:
        native = capture.get(cv2.CAP_PROP_FPS) or 30.0
        step = max(1, round(native / fps))
        index = 0
        while capture.grab():  # sequential decoding: seeking is slower for inter-coded video
            if index % step == 0:
                ok, frame = capture.retrieve()
                if ok:
                    yield index / native, fit(frame, long_side)
            index += 1
    finally:
        capture.release()


def fit(frame: Any, long_side: int) -> Any:
    """``frame`` scaled down (never up) so its long side is at most ``long_side`` px."""
    import cv2

    height, width = frame.shape[:2]
    scale = long_side / max(height, width)
    if scale >= 1:
        return frame
    return cv2.resize(frame, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
