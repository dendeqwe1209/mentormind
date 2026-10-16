"""``scene`` (spec 03 FR-03): shot boundaries by PySceneDetect's ``ContentDetector``.

A single-shot video gives one cut; post-processing (FR-04) splits it into ≤ 15 s parts. Without
the ``scenedetect`` package the method is unavailable and ``fixed_window`` takes over.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from mentormind.capture.video.segmenters.base import Cut, SegmenterUnavailable
from mentormind.capture.video.segmenters.frames import FrameSource, sample_frames
from mentormind.capture.video.segmenters.motion import frame_motion, scored
from mentormind.core.schemas.video import VideoAsset

CONTENT_THRESHOLD = 27.0

#: ``(video, threshold) -> [(start_s, end_s)]`` of the shots.
SceneDetector = Callable[[Path, float], list[tuple[float, float]]]


def detect_scenes(video: Path, threshold: float) -> list[tuple[float, float]]:
    """PySceneDetect ``ContentDetector`` on its OpenCV backend, frames downscaled automatically."""
    try:
        with _without_pyav():
            from scenedetect import SceneManager, open_video
            from scenedetect.detectors import ContentDetector
    except ImportError as exc:
        raise SegmenterUnavailable("thiếu thư viện scenedetect (uv sync --extra video)") from exc
    stream = open_video(str(video))
    manager = SceneManager()
    manager.auto_downscale = True
    manager.add_detector(ContentDetector(threshold=threshold))
    manager.detect_scenes(stream)
    return [(start.get_seconds(), end.get_seconds()) for start, end in manager.get_scene_list()]


@contextmanager
def _without_pyav() -> Iterator[None]:
    """Keep PyAV out of the process while ``scenedetect`` is imported (from Hoàng's branch).

    ``scenedetect`` loads PyAV as an optional backend when it is installed (it is, for
    faster-whisper). Frames are read with OpenCV only, and on macOS the PyAV and OpenCV wheels both
    bundle libavdevice: loading both makes the Objective-C runtime warn of duplicate classes that
    may crash. A ``None`` entry in ``sys.modules`` makes ``import av`` raise ``ImportError``, which
    ``scenedetect`` handles.
    """
    if "av" in sys.modules:  # already loaded in this process: nothing left to keep out
        yield
        return
    sys.modules["av"] = None  # type: ignore[assignment]
    try:
        yield
    finally:
        sys.modules.pop("av", None)


class SceneSegmenter:
    name: Literal["scene"] = "scene"

    def __init__(
        self,
        threshold: float = CONTENT_THRESHOLD,
        *,
        detect: SceneDetector = detect_scenes,
        frames: FrameSource = sample_frames,
    ) -> None:
        self.threshold = threshold
        self._detect = detect
        self._frames = frames

    def cut(self, video: Path, asset: VideoAsset) -> list[Cut]:
        shots = self._detect(video, self.threshold) or [(0.0, asset.duration_s)]
        return scored([Cut(start, end) for start, end in shots], frame_motion(video, frames=self._frames))
