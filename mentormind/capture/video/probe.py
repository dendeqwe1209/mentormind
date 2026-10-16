"""``VideoAsset`` of a raw video (spec 03 FR-01): content id, duration, fps, audio.

ffprobe reads duration, fps and whether there is an audio stream. Without ffprobe (a machine with
no ffmpeg, e.g. a test runner) OpenCV reads duration and fps, and the video counts as silent:
nothing to transcribe, logged.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mentormind.core.schemas.common import DataClassification
from mentormind.core.schemas.video import VideoAsset

log = logging.getLogger(__name__)

#: ``video -> ffprobe's JSON (-show_format -show_streams)``; None when ffprobe is not installed.
StreamReader = Callable[[Path], dict[str, Any] | None]


def video_id_for(path: Path) -> str:
    """``VID-`` + sha256[:12] of the file (spec 03 §3)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return f"VID-{digest.hexdigest()[:12]}"


def ffprobe_json(video: Path) -> dict[str, Any] | None:
    if shutil.which("ffprobe") is None:
        return None
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(video)],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    if out.returncode != 0:
        raise ValueError(f"ffprobe không đọc được {video.name}: {out.stderr.strip()[:200]}")
    data: dict[str, Any] = json.loads(out.stdout)
    return data


def probe_video(
    video: Path,
    *,
    process_id: str | None,
    classification: DataClassification,
    video_id: str | None = None,
    read_streams: StreamReader | None = None,
) -> VideoAsset:
    """Spec 03 §3 ``VideoAsset`` of ``video``.

    Raises:
        FileNotFoundError: no such file.
        ValueError: no video stream, or its duration/fps cannot be read.
    """
    if not video.is_file():
        raise FileNotFoundError(f"Không thấy video {video}")
    info = (read_streams or ffprobe_json)(video)
    if info is None:
        log.warning("Không có ffprobe: đọc %s bằng OpenCV, coi như không có audio", video.name)
        duration, fps, has_audio = _opencv(video)
    else:
        duration, fps, has_audio = _from_ffprobe(info, video)
    return VideoAsset(
        video_id=video_id or video_id_for(video),
        path=str(video),
        duration_s=round(duration, 3),
        fps=round(fps, 3),
        has_audio=has_audio,
        process_id=process_id,
        data_classification=classification,
    )


def _from_ffprobe(info: dict[str, Any], video: Path) -> tuple[float, float, bool]:
    streams = info.get("streams", [])
    picture = next((s for s in streams if s.get("codec_type") == "video"), None)
    if picture is None:
        raise ValueError(f"{video.name} không có luồng hình")
    duration = _float(info.get("format", {}).get("duration")) or _float(picture.get("duration"))
    fps = _rate(picture.get("avg_frame_rate")) or _rate(picture.get("r_frame_rate"))
    if not duration or not fps:
        raise ValueError(f"không đọc được thời lượng/fps của {video.name}")
    return duration, fps, any(s.get("codec_type") == "audio" for s in streams)


def _opencv(video: Path) -> tuple[float, float, bool]:
    import cv2

    capture = cv2.VideoCapture(str(video))
    try:
        frames = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
    finally:
        capture.release()
    if frames <= 0 or fps <= 0:
        raise ValueError(f"không đọc được số khung hình/fps của {video.name}")
    return float(frames / fps), float(fps), False


def _float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "N/A") else None
    except (TypeError, ValueError):
        return None


def _rate(value: Any) -> float | None:
    if not isinstance(value, str) or "/" not in value:
        return _float(value)
    num, den = value.split("/", 1)
    numerator, denominator = _float(num), _float(den)
    return numerator / denominator if numerator and denominator else None
