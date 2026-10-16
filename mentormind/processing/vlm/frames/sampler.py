"""Adaptive frame sampler for one segment clip (spec 04 §2, FR-02b).

1. fps from ``Segment.motion_score``: ``>= 0.6`` -> 8 fps, ``< 0.3`` -> 2 fps, else the default.
2. Frames resized so the long side is 448 px (temporal density over sharpness).
3. Near-duplicates dropped: dHash 64-bit, Hamming distance <= 4 to the last KEPT frame.
4. At most ``max_frames`` frames: above the cap, re-sample evenly down to the cap.

``DataGuard`` runs before the clip is opened: frames are cut only for a destination allowed to
receive them (constitution art. 2).
"""

from __future__ import annotations

from pathlib import Path

import cv2
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from mentormind.core.guard import DataGuard, SupportsCloudFlag
from mentormind.core.schemas.video import Segment
from mentormind.processing.vlm.frames.dedup import drop_near_duplicates

HIGH_MOTION_SCORE = 0.6
LOW_MOTION_SCORE = 0.3
HIGH_MOTION_FPS = 8.0
LOW_MOTION_FPS = 2.0
LONG_SIDE_PX = 448
JPEG_QUALITY = 90


class SampledFrames(BaseModel):
    """Frames chosen for one VLM call, in time order."""

    model_config = ConfigDict(frozen=True)

    paths: list[Path]
    #: Seconds from the start of the clip, one per path.
    timestamps: list[float]
    #: Sampling rate actually used — goes into ``model_info.fps``.
    fps: float = Field(gt=0)


def choose_fps(motion_score: float | None, default_fps: float) -> float:
    """Sampling rate for a segment of the given motion (spec 04 §2)."""
    if motion_score is None:
        return default_fps
    if motion_score >= HIGH_MOTION_SCORE:
        return HIGH_MOTION_FPS
    if motion_score < LOW_MOTION_SCORE:
        return LOW_MOTION_FPS
    return default_fps


def sample_frames(
    segment: Segment,
    destination: SupportsCloudFlag,
    *,
    out_dir: Path,
    default_fps: float,
    max_frames: int,
) -> SampledFrames:
    """Cut the frames of ``segment`` that will be sent to ``destination``.

    Raises:
        ConfidentialDataError: the segment may not be sent to ``destination`` (checked before
            the clip is opened).
        ValueError: the clip cannot be decoded.
    """
    DataGuard.check(segment.data_classification, destination)
    target_fps = choose_fps(segment.motion_score, default_fps)
    decoded, native_fps = _decode_at_rate(Path(segment.clip_path), target_fps)
    kept = drop_near_duplicates(decoded)
    sampling_fps = min(target_fps, native_fps)
    if len(kept) > max_frames:
        sampling_fps *= max_frames / len(kept)
        kept = _evenly(kept, max_frames)

    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i, (_, image) in enumerate(kept):
        path = out_dir / f"{segment.segment_id}_f{i:03d}.jpg"
        image.save(path, format="JPEG", quality=JPEG_QUALITY)
        paths.append(path)
    return SampledFrames(paths=paths, timestamps=[t for t, _ in kept], fps=round(sampling_fps, 3))


def _decode_at_rate(clip: Path, fps: float) -> tuple[list[tuple[float, Image.Image]], float]:
    """Decode ``clip`` keeping one frame every ``1/fps`` s; also return the native fps."""
    capture = cv2.VideoCapture(str(clip))
    if not capture.isOpened():
        raise ValueError(f"Cannot open clip {clip}")
    try:
        native_fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
        step = 1.0 / fps
        next_t = 0.0
        frames: list[tuple[float, Image.Image]] = []
        index = 0
        while True:
            ok, bgr = capture.read()
            if not ok:
                break
            t = index / native_fps
            index += 1
            if t + 1e-6 < next_t:
                continue
            frames.append((round(t, 3), _to_image(bgr)))
            next_t += step
            while next_t <= t:  # target rate above the native rate: never fall behind
                next_t += step
    finally:
        capture.release()
    if not frames:
        raise ValueError(f"No decodable frame in {clip}")
    return frames, native_fps


def _to_image(bgr: cv2.typing.MatLike) -> Image.Image:
    height, width = bgr.shape[:2]
    scale = LONG_SIDE_PX / max(height, width)
    if scale < 1.0:
        bgr = cv2.resize(bgr, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
    return Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


def _evenly(frames: list[tuple[float, Image.Image]], count: int) -> list[tuple[float, Image.Image]]:
    """``count`` frames spread evenly over ``frames``, first and last included."""
    if count <= 1:
        return frames[:count]
    last = len(frames) - 1
    return [frames[round(i * last / (count - 1))] for i in range(count)]
