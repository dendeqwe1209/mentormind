"""``VideoCapturePipeline`` (spec 03 FR-09): probe → cut → post-process → keyframes + clips → transcribe.

The CLI (``knowhow video``, ``knowhow vlm describe --video``) and the API (spec 08) run videos
through this one class. Each run writes ``video.json``, ``segments.json`` and, when it transcribes,
``transcript.json``; per-run resources (video captures, the hand detector) are released when the
step ends, while the ASR model stays loaded for the next run (FR-07c).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from mentormind.capture.video import store
from mentormind.capture.video.media import export
from mentormind.capture.video.postprocess import postprocess
from mentormind.capture.video.probe import probe_video
from mentormind.capture.video.segmenters import WINDOW_S, Method, Segmenter, build_segmenter, cut_with_fallback
from mentormind.capture.video.transcribe import AudioExtractor, extract_audio, transcribe_video
from mentormind.core.config import Settings
from mentormind.core.providers.asr import ASRProvider, get_asr_provider
from mentormind.core.schemas.common import DataClassification
from mentormind.core.schemas.video import Segment, TranscriptSegment, VideoAsset

Stage = Literal["cut", "transcribe"]
#: ``(stage, done, total)``: segments exported for ``cut``, seconds of audio heard for ``transcribe``.
StageProgress = Callable[[Stage, float, float], None]


@dataclass(frozen=True)
class CaptureResult:
    asset: VideoAsset
    segments: list[Segment]
    #: Every line of the video's ``transcript.json`` (inline and cued recall), in time order.
    transcript: list[TranscriptSegment]
    method: Method
    #: The method that actually cut (FR-03 fallback); differs from ``method`` when a library was missing.
    method_used: Method
    #: Wall time of each step, seconds: probe, cut, media, transcribe.
    seconds: dict[str, float] = field(default_factory=dict)


class VideoCapturePipeline:
    def __init__(
        self,
        settings: Settings,
        *,
        build: Callable[[Method], Segmenter] | None = None,
        asr: Callable[[], ASRProvider] | None = None,
        extract: AudioExtractor = extract_audio,
        window_s: float = WINDOW_S,
    ) -> None:
        self.settings = settings
        self._build = build or (lambda method: build_segmenter(method, settings, window_s=window_s))
        self._asr = asr or (lambda: get_asr_provider(settings))
        self._extract = extract

    def run(
        self,
        video: Path,
        *,
        work_dir: Path,
        process_id: str | None,
        classification: DataClassification,
        method: Method = "hand_activity",
        transcribe: bool = True,
        video_id: str | None = None,
        progress: StageProgress | None = None,
    ) -> CaptureResult:
        """Cut ``video`` (and transcribe it when ``transcribe`` and it has audio); write its files."""
        seconds: dict[str, float] = {}
        started = time.perf_counter()
        asset = probe_video(video, process_id=process_id, classification=classification, video_id=video_id)
        store.write_asset(work_dir, asset)
        seconds["probe"] = time.perf_counter() - started

        started = time.perf_counter()
        if progress is not None:
            progress("cut", 0, 0)  # segments not known yet; finding them takes 10-30 s on CPU (AC-15)
        cuts, used = cut_with_fallback(method, video, asset, build=self._build)
        cuts = postprocess(cuts, asset.duration_s)
        seconds["cut"] = time.perf_counter() - started

        started = time.perf_counter()
        segments = export(
            video,
            cuts,
            asset=asset,
            method=used,
            work_dir=work_dir,
            progress=None if progress is None else lambda done, total: progress("cut", done, total),
        )
        store.write_segments(store.segments_path(work_dir, asset.video_id), segments)
        seconds["media"] = time.perf_counter() - started

        if transcribe and asset.has_audio:
            started = time.perf_counter()
            if progress is not None:
                progress("transcribe", 0, asset.duration_s)  # before the audio and the ASR model load (AC-15)
            transcribe_video(
                asset,
                self._asr(),
                work_dir=work_dir,
                language=self.settings.asr_language,
                progress=None if progress is None else lambda done, total: progress("transcribe", done, total),
                extract=self._extract,
            )
            seconds["transcribe"] = time.perf_counter() - started
        transcript = store.read_transcript(work_dir, asset.video_id)
        return CaptureResult(asset, segments, transcript, method, used, seconds)
