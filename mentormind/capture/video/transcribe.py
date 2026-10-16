"""Spec 03 FR-07/07b: the expert's speech as timed sentences in ``transcript.json``.

The audio is taken out of the video by ffmpeg (16 kHz mono WAV, streamed — the video is never held
in memory) and handed to the ASR provider of ``KNOWHOW_ASR_PROVIDER`` (FR-07c). Sentences are cut
from the word timestamps: at a sentence mark (. ? ! …), at a pause of 0.8 s or more, at the end of each
stretch Whisper returns, or past 15 s at the next word boundary (never inside a word). Every line carries the video's label (AC-07).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from mentormind.capture.video import store
from mentormind.core.providers.asr import ASRProvider, ASRResult, ASRWord, Progress
from mentormind.core.schemas.video import TranscriptSegment, VideoAsset

PAUSE_S = 0.8
MAX_SENTENCE_S = 15.0
_SENTENCE_END = re.compile(r"[.?!…]$")
_CLOSERS = "\"'”’)]»"

#: ``(video, wav)``: write the video's audio as 16 kHz mono WAV.
AudioExtractor = Callable[[Path, Path], None]


def extract_audio(video: Path, wav: Path) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("Cần ffmpeg trong PATH để tách audio (spec 03 FR-07): brew install ffmpeg.")
    wav.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
         "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)],
        check=True,
    )  # fmt: skip


def sentences(result: ASRResult) -> list[tuple[float, float, str]]:
    """``(t_start, t_end, text)`` of every sentence heard (AC-10)."""
    out: list[tuple[float, float, str]] = []
    current: list[ASRWord] = []

    def flush() -> None:
        # Whisper's word tokens carry their own leading space where the language has one: joining them
        # with spaces would split Thai (or Chinese, Japanese) into syllables.
        text = " ".join("".join(w.text for w in current).split())
        if text:
            out.append((current[0].t_start, current[-1].t_end, text))
        current.clear()

    for segment in result.segments:
        if not segment.words:  # an engine without word timestamps: the stretch is one sentence
            if segment.text.strip():
                out.append((segment.t_start, segment.t_end, segment.text.strip()))
            continue
        for word in segment.words:
            too_long = word.t_end - current[0].t_start > MAX_SENTENCE_S if current else False
            # A long sentence is cut only where a word starts (a token with a leading space): never
            # inside a word of a language written without spaces (Thai "ครั|บ").
            if current and (word.t_start - current[-1].t_end >= PAUSE_S or (too_long and word.text[:1].isspace())):
                flush()
            current.append(word)
            if _SENTENCE_END.search(word.text.strip().rstrip(_CLOSERS)):
                flush()
        flush()  # Whisper ends a stretch of speech at a phrase boundary
    return out


def transcribe_video(
    asset: VideoAsset,
    asr: ASRProvider,
    *,
    work_dir: Path,
    language: str | None = None,
    progress: Progress | None = None,
    extract: AudioExtractor = extract_audio,
) -> list[TranscriptSegment]:
    """The inline speech of ``asset`` (FR-07); ``[]`` for a video without audio (AC-05).

    Rewrites the video's inline lines in ``transcript.json`` and keeps its ``cued_recall`` lines.
    """
    if not asset.has_audio:
        return []
    wav = store.video_dir(work_dir, asset.video_id) / "audio.wav"
    extract(Path(asset.path), wav)
    try:
        result = asr.transcribe(wav, classification=asset.data_classification, language=language, progress=progress)
    finally:
        wav.unlink(missing_ok=True)
    lines = _lines(asset, result, source="inline", offset=0.0)
    recalled = [line for line in store.read_transcript(work_dir, asset.video_id) if line.source == "cued_recall"]
    store.write_transcript(work_dir, asset.video_id, [*recalled, *lines])
    return lines


def transcribe_recall(
    audio: Path,
    *,
    video_id: str,
    offset: float,
    asr: ASRProvider,
    work_dir: Path,
    language: str | None = None,
) -> list[TranscriptSegment]:
    """The expert's video-cued recall of a silent video (FR-07b), stored in its ``transcript.json``.

    A recording owns the video time it covers (``offset`` to ``offset`` + its length): recalled lines
    that start there are replaced, the others and every inline line are kept (AC-14). ASR splits
    the same audio differently on each run, so words cannot tell a re-run from a new recording.

    Raises:
        FileNotFoundError: no such video (never probed) or no such audio file; nothing is written (AC-08).
    """
    asset = store.read_asset(work_dir, video_id)
    if not audio.is_file():
        raise FileNotFoundError(f"Không thấy file ghi âm {audio}")
    result = asr.transcribe(audio, classification=asset.data_classification, language=language)
    lines = _lines(asset, result, source="cued_recall", offset=offset)
    end = offset + result.duration_s
    kept = [
        line
        for line in store.read_transcript(work_dir, video_id)
        if line.source != "cued_recall" or not offset <= line.t_start < end
    ]
    store.write_transcript(work_dir, video_id, [*kept, *lines])
    return lines


def _lines(asset: VideoAsset, result: ASRResult, *, source: str, offset: float) -> list[TranscriptSegment]:
    return [
        TranscriptSegment(
            video_id=asset.video_id,
            t_start=round(start + offset, 3),
            t_end=round(end + offset, 3),
            text=text,
            language=result.language,
            source="cued_recall" if source == "cued_recall" else "inline",
            data_classification=asset.data_classification,
        )
        for start, end, text in sentences(result)
    ]
