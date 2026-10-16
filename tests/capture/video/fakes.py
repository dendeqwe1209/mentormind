"""Synthetic videos and stand-ins for ffmpeg/ffprobe (spec 03 tests).

Tests never call ffmpeg, MediaPipe, PySceneDetect or Whisper: clips are small synthetic videos made
with OpenCV, ffprobe's answer is built from OpenCV's reading of the file, and the detectors and the
ASR provider are injected through constructors.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest

from mentormind.capture.video import media, probe


def synthetic_video(path: Path, seconds: float, *, fps: int = 4, size: tuple[int, int] = (64, 48)) -> Path:
    """An mp4 whose frames get brighter over time (OpenCV only, no ffmpeg needed)."""
    width, height = size
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter.fourcc(*"mp4v"), fps, (width, height))
    for i in range(round(seconds * fps)):
        writer.write(np.full((height, width, 3), (i * 9) % 256, dtype=np.uint8))
    writer.release()
    return path


def fake_ffmpeg(monkeypatch: pytest.MonkeyPatch, *, audio: bool = False) -> None:
    """Clips: synthetic videos of the cut's length; ffprobe: OpenCV's reading, with an audio stream if asked."""
    monkeypatch.setattr(media.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(media, "cut_clip", lambda video, clip, start, end, **_: synthetic_video(clip, end - start))

    def streams(video: Path) -> dict[str, Any]:
        capture = cv2.VideoCapture(str(video))
        frames, fps = capture.get(cv2.CAP_PROP_FRAME_COUNT), capture.get(cv2.CAP_PROP_FPS)
        capture.release()
        tracks = [{"codec_type": "video", "avg_frame_rate": f"{round(fps)}/1"}]
        return {
            "format": {"duration": str(frames / fps)},
            "streams": tracks + ([{"codec_type": "audio"}] if audio else []),
        }

    monkeypatch.setattr(probe, "ffprobe_json", streams)
