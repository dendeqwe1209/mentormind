"""spec 04 T04-2 / AC-10 — adaptive fps, frame cap, resize, guard before decoding."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image
from pydantic import BaseModel

from mentormind.core.guard import ConfidentialDataError
from mentormind.core.schemas.common import DataClassification
from mentormind.core.schemas.video import Segment
from mentormind.processing.vlm.frames import (
    LONG_SIDE_PX,
    choose_fps,
    sample_frames,
)


class Destination(BaseModel):
    name: str = "local_openai"
    is_cloud: bool = False


def write_clip(path: Path, frames: list[np.ndarray], fps: float) -> Path:
    height, width = frames[0].shape[:2]
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter.fourcc(*"mp4v"), fps, (width, height))
    for frame in frames:
        writer.write(frame)
    writer.release()
    return path


def noise_frames(count: int, size: tuple[int, int] = (120, 160), seed: int = 0) -> list[np.ndarray]:
    """Every frame different: random blocks, upscaled so compression keeps them distinct."""
    rng = np.random.default_rng(seed)
    height, width = size
    frames = []
    for _ in range(count):
        blocks = rng.integers(0, 256, (height // 8, width // 8, 3), dtype=np.uint8)
        frames.append(cv2.resize(blocks, (width, height), interpolation=cv2.INTER_NEAREST))
    return frames


def still_frames(count: int, size: tuple[int, int] = (120, 160)) -> list[np.ndarray]:
    """Identical frames with structure (a flat image would make dHash bits noise-driven)."""
    height, width = size
    base = np.zeros((height, width, 3), dtype=np.uint8)
    base[:, :, 1] = np.linspace(0, 255, width, dtype=np.uint8)[None, :]
    cv2.rectangle(base, (30, 30), (90, 90), (255, 255, 255), -1)
    return [base.copy() for _ in range(count)]


def segment_for(clip: Path, motion: float | None, label: str = "synthetic") -> Segment:
    return Segment(
        segment_id="VID-TEST-S001",
        video_id="VID-TEST",
        index=1,
        t_start=0.0,
        t_end=10.0,
        method="fixed_window",
        motion_score=motion,
        keyframes=[],
        clip_path=str(clip),
        data_classification=DataClassification(label),
    )


@pytest.mark.parametrize(
    ("motion", "expected"),
    [(0.8, 8.0), (0.6, 8.0), (0.59, 4.0), (0.3, 4.0), (0.29, 2.0), (0.0, 2.0), (None, 4.0)],
)
def test_ac_10_fps_follows_motion_score(motion: float | None, expected: float) -> None:
    assert choose_fps(motion, default_fps=4.0) == expected


def test_ac_10_high_motion_segment_is_sampled_at_8fps(tmp_path: Path) -> None:
    clip = write_clip(tmp_path / "fast.mp4", noise_frames(60), fps=30)  # 2 s
    result = sample_frames(
        segment_for(clip, motion=0.8),
        Destination(),
        out_dir=tmp_path / "out",
        default_fps=4.0,
        max_frames=48,
    )
    assert result.fps == 8.0
    assert len(result.paths) == 16
    assert result.timestamps == sorted(result.timestamps)
    steps = np.diff(result.timestamps)
    assert np.allclose(steps, 1 / 8, atol=1 / 30 + 1e-6)


def test_ac_10_identical_frames_collapse_to_one(tmp_path: Path) -> None:
    clip = write_clip(tmp_path / "still.mp4", still_frames(90), fps=30)  # 3 s
    result = sample_frames(
        segment_for(clip, motion=0.8),
        Destination(),
        out_dir=tmp_path / "out",
        default_fps=4.0,
        max_frames=48,
    )
    assert len(result.paths) == 1


def test_ac_10_long_clip_is_capped_at_max_frames(tmp_path: Path) -> None:
    clip = write_clip(tmp_path / "long.mp4", noise_frames(200, seed=1), fps=10)  # 20 s
    result = sample_frames(
        segment_for(clip, motion=0.8),  # 8 fps x 20 s = 160 candidate frames
        Destination(),
        out_dir=tmp_path / "out",
        default_fps=4.0,
        max_frames=48,
    )
    assert len(result.paths) == 48
    assert result.timestamps[0] == 0.0 and result.timestamps[-1] >= 19.0
    assert result.fps == pytest.approx(8.0 * 48 / 160, rel=0.05)


def test_frames_are_resized_to_448_long_side_as_jpeg(tmp_path: Path) -> None:
    clip = write_clip(tmp_path / "hd.mp4", noise_frames(10, size=(720, 1280)), fps=10)
    result = sample_frames(
        segment_for(clip, motion=None),
        Destination(),
        out_dir=tmp_path / "out",
        default_fps=4.0,
        max_frames=48,
    )
    with Image.open(result.paths[0]) as image:
        assert image.format == "JPEG"
        assert max(image.size) == LONG_SIDE_PX
        assert image.size == (448, 252)


def test_guard_runs_before_the_clip_is_opened(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.mp4"
    with pytest.raises(ConfidentialDataError):
        sample_frames(
            segment_for(missing, motion=None, label="factory_confidential"),
            Destination(name="openrouter", is_cloud=True),
            out_dir=tmp_path / "out",
            default_fps=4.0,
            max_frames=48,
        )
    assert not (tmp_path / "out").exists()
