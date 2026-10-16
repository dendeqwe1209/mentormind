"""``motion_score`` of cuts from frame differences (spec 03 FR-03, for ``scene`` and ``fixed_window``).

Grey frames 160 px wide at 4 fps; the motion of an instant is the mean absolute difference with the
previous frame (0..255). A cut's score = its mean motion / 20, capped at 1: 20 grey levels per pixel
on average is already brisk movement at that size.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from mentormind.capture.video.segmenters.base import Cut
from mentormind.capture.video.segmenters.frames import FrameSource, sample_frames

MOTION_FPS = 4.0
MOTION_LONG_SIDE = 160
FULL_MOTION = 20.0


def frame_motion(video: Path, *, frames: FrameSource = sample_frames) -> list[tuple[float, float]]:
    """``(seconds, mean absolute grey difference with the previous sample)`` along the video."""
    import cv2
    import numpy as np

    samples: list[tuple[float, float]] = []
    previous = None
    for t, frame in frames(video, MOTION_FPS, MOTION_LONG_SIDE):
        grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.int16)
        if previous is not None and previous.shape == grey.shape:
            samples.append((t, float(np.abs(grey - previous).mean())))
        previous = grey
    return samples


def scored(cuts: Sequence[Cut], samples: Sequence[tuple[float, float]], full: float = FULL_MOTION) -> list[Cut]:
    """``cuts`` with ``motion_score`` = mean of the samples inside each, / ``full``, capped at 1."""
    out = []
    for cut in cuts:
        inside = [value for t, value in samples if cut.t_start <= t < cut.t_end]
        score = min(1.0, (sum(inside) / len(inside)) / full) if inside else None
        out.append(replace(cut, motion_score=None if score is None else round(score, 3)))
    return out
