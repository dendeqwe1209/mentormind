"""Where spec 03 keeps a video's files: ``<work>/video/<video_id>/`` (spec 03 FR-02, FR-07).

``video.json`` (``VideoAsset``), ``segments.json`` (list of ``Segment``), ``transcript.json`` (list of
``TranscriptSegment``), ``keyframes/``, ``clips/``. Spec 04 and the API (spec 08) read them back.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, TypeAdapter

from mentormind.core.schemas.video import Segment, TranscriptSegment, VideoAsset

_SEGMENTS = TypeAdapter(list[Segment])
_LINES = TypeAdapter(list[TranscriptSegment])


def video_dir(work_dir: Path, video_id: str) -> Path:
    return work_dir / "video" / video_id


def asset_path(work_dir: Path, video_id: str) -> Path:
    return video_dir(work_dir, video_id) / "video.json"


def segments_path(work_dir: Path, video_id: str) -> Path:
    return video_dir(work_dir, video_id) / "segments.json"


def transcript_path(work_dir: Path, video_id: str) -> Path:
    return video_dir(work_dir, video_id) / "transcript.json"


def read_asset(work_dir: Path, video_id: str) -> VideoAsset:
    """The video's ``VideoAsset``.

    Raises:
        FileNotFoundError: the video was never probed or uploaded.
    """
    path = asset_path(work_dir, video_id)
    if not path.is_file():
        raise FileNotFoundError(f"Không có video {video_id} (thiếu {path}; chạy `knowhow video segment` trước).")
    return VideoAsset.model_validate_json(path.read_text(encoding="utf-8"))


def write_asset(work_dir: Path, asset: VideoAsset) -> Path:
    path = asset_path(work_dir, asset.video_id)
    _write(path, asset.model_dump_json(indent=2))
    return path


def read_segments(path: Path) -> list[Segment]:
    """The segments of a ``segments.json``.

    Raises:
        FileNotFoundError: no such file.
        ValueError: the file lists no segment.
    """
    if not path.is_file():
        raise FileNotFoundError(f"Không thấy {path} (`knowhow video segment` chưa chạy). Dùng --video <file>.")
    loaded = _SEGMENTS.validate_json(path.read_text(encoding="utf-8"))
    if not loaded:
        raise ValueError(f"{path} không có đoạn nào.")
    return loaded


def write_segments(path: Path, segments: Sequence[Segment]) -> None:
    _write(path, _dump(segments))


def read_transcript(work_dir: Path, video_id: str) -> list[TranscriptSegment]:
    """The video's transcript lines; ``[]`` when none was written."""
    path = transcript_path(work_dir, video_id)
    return _LINES.validate_json(path.read_text(encoding="utf-8")) if path.is_file() else []


def write_transcript(work_dir: Path, video_id: str, lines: Sequence[TranscriptSegment]) -> Path:
    path = transcript_path(work_dir, video_id)
    ordered: list[TranscriptSegment] = sorted(lines, key=lambda line: (line.t_start, line.t_end))
    _write(path, _dump(ordered))
    return path


def _dump(items: Sequence[BaseModel]) -> str:
    return json.dumps([item.model_dump(mode="json") for item in items], ensure_ascii=False, indent=2)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.write_text(text, encoding="utf-8")
    part.replace(path)
