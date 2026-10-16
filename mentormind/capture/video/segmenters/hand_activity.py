"""``hand_activity`` (spec 03 FR-03, Should): cut where the operator's hands rest.

MediaPipe Tasks ``HandLandmarker`` on the CPU, frames 256 px at 5 fps. The energy of an instant is
the mean speed of the wrists (landmark 0) between the last two frames with hands, in frame widths
per second. Hands out of view for 0.4 s or more = rest; a shorter gap is a missed detection, not a
rest. A boundary sits in the middle of every rest of ≥ 0.4 s with activity on both sides. Hands
seen in under 10% of the frames (a robot cell, an interview: LASI 3.3%) means the method does not
apply: the chain moves on to ``scene`` (AC-13). ``motion_score`` = mean wrist speed / 0.5.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx

from mentormind.capture.video.segmenters.base import Cut, SegmenterUnavailable
from mentormind.capture.video.segmenters.frames import FrameSource, sample_frames
from mentormind.capture.video.segmenters.motion import scored
from mentormind.core.schemas.video import VideoAsset

HAND_FPS = 5.0
HAND_LONG_SIDE = 256
REST_SPEED = 0.05  # frame widths per second
MIN_REST_S = 0.4
MIN_PRESENCE = 0.10  # share of frames with a hand below which the cuts would be noise
FULL_SPEED = 0.5  # motion_score 1
HAND_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
)
HAND_MODEL_SHA256 = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"

Point = tuple[float, float]


class HandDetector(Protocol):
    def wrists(self, frame: Any, t: float) -> list[Point]:
        """Normalised (x, y) of the wrist of every hand seen in ``frame`` (taken at ``t`` s)."""
        ...

    def close(self) -> None: ...


def ensure_hand_model(path: Path) -> Path:
    """``path``, after downloading and checking the pinned MediaPipe hand model if it is missing."""
    if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == HAND_MODEL_SHA256:
        return path
    try:
        response = httpx.get(HAND_MODEL_URL, follow_redirects=True, timeout=60)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise SegmenterUnavailable(
            f"không tải được model bàn tay ({exc!r}); tải thủ công {HAND_MODEL_URL} về {path}"
        ) from exc
    if hashlib.sha256(response.content).hexdigest() != HAND_MODEL_SHA256:
        raise SegmenterUnavailable("model bàn tay tải về sai checksum SHA-256, từ chối dùng")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    return path


class MediaPipeHands:
    """``HandLandmarker`` in VIDEO mode on the CPU; one per run, closed after it."""

    def __init__(self, model: Path) -> None:
        try:
            import mediapipe as mp
            from mediapipe.tasks.python import vision
            from mediapipe.tasks.python.core.base_options import BaseOptions
        except (ImportError, OSError) as exc:  # OSError: its sounddevice needs PortAudio on Linux
            raise SegmenterUnavailable(f"thiếu MediaPipe ({exc}); uv sync --extra video") from exc
        delegate = getattr(BaseOptions, "Delegate", None)
        base = BaseOptions(model_asset_path=str(ensure_hand_model(model)))
        if delegate is not None:
            base = BaseOptions(model_asset_path=base.model_asset_path, delegate=delegate.CPU)
        options = vision.HandLandmarkerOptions(base_options=base, running_mode=vision.RunningMode.VIDEO, num_hands=2)
        self._image = mp.Image
        self._srgb = mp.ImageFormat.SRGB
        self._landmarker = vision.HandLandmarker.create_from_options(options)

    def wrists(self, frame: Any, t: float) -> list[Point]:
        import cv2

        image = self._image(image_format=self._srgb, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        result = self._landmarker.detect_for_video(image, int(t * 1000))
        return [(hand[0].x, hand[0].y) for hand in result.hand_landmarks]

    def close(self) -> None:
        self._landmarker.close()


def wrist_speeds(
    track: Sequence[tuple[float, list[Point]]], min_rest_s: float = MIN_REST_S
) -> list[tuple[float, float]]:
    """``(seconds, wrist speed)`` along the video; 0 while hands stay out of view ≥ ``min_rest_s``."""
    speeds: list[tuple[float, float]] = []
    last: tuple[float, list[Point]] | None = None  # the last frame with hands
    for t, hands in track:
        if not hands:
            if last is None or t - last[0] >= min_rest_s:
                speeds.append((t, 0.0))
            continue  # a shorter gap is a missed detection: no sample
        if last is not None and t > last[0]:
            moved = [min(math.dist(w, p) for p in last[1]) for w in hands]
            speeds.append((t, sum(moved) / len(moved) / (t - last[0])))
        last = (t, hands)
    return speeds


def rest_boundaries(
    speeds: Sequence[tuple[float, float]], *, rest_speed: float = REST_SPEED, min_rest_s: float = MIN_REST_S
) -> list[float]:
    """Middle of every rest (speed < ``rest_speed``) of ≥ ``min_rest_s`` with activity before and after it."""
    bounds: list[float] = []
    i = 0
    while i < len(speeds):
        if speeds[i][1] >= rest_speed:
            i += 1
            continue
        j = i
        while j + 1 < len(speeds) and speeds[j + 1][1] < rest_speed:
            j += 1
        start = speeds[i - 1][0] if i > 0 else speeds[i][0]  # a sample covers the time since the previous one
        end = speeds[j][0]
        if i > 0 and j + 1 < len(speeds) and end - start >= min_rest_s:
            bounds.append(round((start + end) / 2, 3))
        i = j + 1
    return bounds


class HandActivitySegmenter:
    name: Literal["hand_activity"] = "hand_activity"

    def __init__(
        self,
        *,
        model: Path | None = None,
        detector: Callable[[], HandDetector] | None = None,
        frames: FrameSource = sample_frames,
        fps: float = HAND_FPS,
        long_side: int = HAND_LONG_SIDE,
    ) -> None:
        if detector is None:
            if model is None:
                raise ValueError("HandActivitySegmenter needs a model path or a detector")
            hand_model = model
            detector = lambda: MediaPipeHands(hand_model)  # noqa: E731 - built per run, closed after it
        self._detector = detector
        self._frames = frames
        self.fps = fps
        self.long_side = long_side

    def cut(self, video: Path, asset: VideoAsset) -> list[Cut]:
        detector = self._detector()  # SegmenterUnavailable: the chain moves on to `scene`
        try:
            track = [(t, detector.wrists(frame, t)) for t, frame in self._frames(video, self.fps, self.long_side)]
        finally:
            detector.close()
        presence = sum(1 for _, hands in track if hands) / len(track) if track else 0.0
        if presence < MIN_PRESENCE:
            raise SegmenterUnavailable(f"hầu như không thấy tay ({presence:.0%} số khung, cần ≥ {MIN_PRESENCE:.0%})")
        speeds = wrist_speeds(track)
        edges = [0.0, *[b for b in rest_boundaries(speeds) if 0 < b < asset.duration_s], asset.duration_s]
        cuts = [Cut(start, end) for start, end in zip(edges, edges[1:], strict=False) if end > start]
        return scored(cuts, speeds, full=FULL_SPEED)
