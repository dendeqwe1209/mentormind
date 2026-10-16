"""Keyframes (spec 03 FR-05) and clips (FR-06) of a video's segments.

Both are cached under ``<work>/video/<video_id>/``; a cached file is reused only while its segment
keeps the same bounds (``segments.json`` of the previous run), so cutting again with another method
never shows a stale clip. Clips are always re-encoded H.264 by ffmpeg: ``-c copy`` would cut at the
source's keyframes and keep codecs a browser may not play (the UI of spec 08 plays them). They keep
the video's sound as AAC, so a reviewer hears the expert; ``clips/.format`` marks the clip format, and
clips of an older format (silent ones) are redone.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from mentormind.capture.video import store
from mentormind.capture.video.segmenters.base import Cut, Method
from mentormind.capture.video.segmenters.frames import fit
from mentormind.core.schemas.video import Segment, VideoAsset

KEYFRAME_LONG_SIDE = 768  # spec 03 FR-05
KEYFRAME_END_MARGIN_S = 0.05
KEYFRAME_RETRY_BACK_S = 0.5
CLIP_WIDTH = 640  # the VLM only ever sees 448 px frames
#: Bump when the clip encoding changes: clips of another format are redone (AC-16).
CLIP_FORMAT = "h264-aac-1"


def segment_id(video_id: str, index: int) -> str:
    return f"{video_id}-S{index:03d}"


def require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("Cần ffmpeg trong PATH để cắt clip (spec 03 FR-06): brew install ffmpeg.")


def cut_clip(video: Path, clip: Path, start: float, end: float, *, audio: bool) -> None:
    """``[start, end]`` of ``video`` as a browser-playable H.264 mp4, with its sound as AAC if ``audio`` (FR-06)."""
    clip.parent.mkdir(parents=True, exist_ok=True)
    part = clip.with_suffix(".part.mp4")
    sound = ["-map", "0:v:0", "-map", "0:a:0", "-c:a", "aac", "-b:a", "128k"] if audio else ["-an"]
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{start:.3f}", "-i", str(video), "-t", f"{end - start:.3f}",
            *sound, "-vf", f"scale={CLIP_WIDTH}:-2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(part),
        ],
        check=True,
    )  # fmt: skip
    part.replace(clip)


class FrameReader:
    """Frames of a video by time; the file is opened on first use, so cached keyframes cost nothing."""

    def __init__(self, video: Path) -> None:
        self._video = video
        self._capture: Any = None

    def at(self, t: float) -> Any:
        import cv2

        if self._capture is None:
            self._capture = cv2.VideoCapture(str(self._video))
        self._capture.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = self._capture.read()
        return frame if ok else None

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None


def keyframes(frames: FrameReader, out_dir: Path, segment_id: str, start: float, end: float) -> list[Path]:
    """Start, middle and end of a segment as JPG, long side at most 768 px (FR-05)."""
    import cv2

    out_dir.mkdir(parents=True, exist_ok=True)
    # The last one sits just before ``end``: the frame at ``end`` opens the next segment.
    times = (start, (start + end) / 2, max(start, end - KEYFRAME_END_MARGIN_S))
    paths = []
    for position, t in enumerate(times):
        path = out_dir / f"{segment_id}_k{position}.jpg"
        if not path.exists():
            frame = frames.at(t)
            if frame is None and t > start:  # the very end of a file is not always seekable
                frame = frames.at(max(start, t - KEYFRAME_RETRY_BACK_S))
            if frame is None:  # unreadable position: one keyframe fewer, the segment itself is fine
                continue
            cv2.imwrite(str(path), fit(frame, KEYFRAME_LONG_SIDE))
        paths.append(path)
    return paths


def export(
    video: Path,
    cuts: Sequence[Cut],
    *,
    asset: VideoAsset,
    method: Method,
    work_dir: Path,
    progress: Callable[[int, int], None] | None = None,
) -> list[Segment]:
    """The segments of ``cuts``, each with its clip and 3 keyframes; their label is the video's (AC-07)."""
    require_ffmpeg()
    folder = store.video_dir(work_dir, asset.video_id)
    previous = _previous_bounds(work_dir, asset.video_id)
    marker = folder / "clips" / ".format"
    fresh_format = marker.is_file() and marker.read_text().strip() == CLIP_FORMAT
    frames = FrameReader(video)
    segments = []
    try:
        for index, cut in enumerate(cuts, start=1):
            sid = segment_id(asset.video_id, index)
            bounds = (round(cut.t_start, 3), round(cut.t_end, 3))
            clip = folder / "clips" / f"{sid}.mp4"
            if previous.get(sid) != bounds:  # another cut of this video: its files are stale
                _forget(folder, sid)
            if not fresh_format:  # made by an older version (silent): redo
                clip.unlink(missing_ok=True)
            if not clip.exists():
                cut_clip(video, clip, *bounds, audio=asset.has_audio)
            shots = keyframes(frames, folder / "keyframes", sid, *bounds)
            segments.append(
                Segment(
                    segment_id=sid,
                    video_id=asset.video_id,
                    index=index,
                    t_start=bounds[0],
                    t_end=bounds[1],
                    method=method,
                    motion_score=cut.motion_score,
                    keyframes=[str(path) for path in shots],
                    clip_path=str(clip),
                    data_classification=asset.data_classification,
                )
            )
            if progress is not None:
                progress(index, len(cuts))
    finally:
        frames.close()
    if segments:
        marker.write_text(CLIP_FORMAT + "\n")
    return segments


def _previous_bounds(work_dir: Path, video_id: str) -> dict[str, tuple[float, float]]:
    try:
        return {
            s.segment_id: (s.t_start, s.t_end) for s in store.read_segments(store.segments_path(work_dir, video_id))
        }
    except (FileNotFoundError, ValueError):
        return {}


def _forget(folder: Path, sid: str) -> None:
    (folder / "clips" / f"{sid}.mp4").unlink(missing_ok=True)
    for path in (folder / "keyframes").glob(f"{sid}_k*.jpg"):
        path.unlink()
