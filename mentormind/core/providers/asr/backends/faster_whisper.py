"""``faster_whisper`` — Whisper on CTranslate2, local and CPU-only by default (spec 03 FR-07).

The model is loaded on the first call (downloaded once from the Hugging Face hub into its cache)
and kept by this instance; ``get_asr_provider`` keeps one instance per configuration, so every job
of the process shares it. Calls are serialised: one CTranslate2 model, one decoding at a time.
The ``faster_whisper`` package (extra ``video``) is imported only when the model is loaded.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Self

from mentormind.core.providers.asr.base import ASRProvider, Progress
from mentormind.core.providers.asr.catalog import default_asr_model
from mentormind.core.providers.asr.models import ASRSegment, ASRWord
from mentormind.core.providers.asr.registry import register_asr
from mentormind.core.providers.errors import ProviderConfigError, ProviderError
from mentormind.core.providers.models import ProviderConfig
from mentormind.core.providers.transport import HttpClient

#: ``(model, device, compute_type) -> engine`` with a faster-whisper ``transcribe`` method.
EngineFactory = Callable[[str, str, str], Any]


def load_whisper(model: str, device: str, compute_type: str) -> Any:
    """A faster-whisper ``WhisperModel`` (first use downloads the model)."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise ProviderConfigError("Thiếu thư viện faster-whisper: uv sync --extra video.") from exc
    try:
        return WhisperModel(model, device=device, compute_type=compute_type)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ProviderConfigError(f"Không nạp được model Whisper {model!r} ({device}, {compute_type}): {exc}") from exc


@register_asr("faster_whisper")
class FasterWhisperASR(ASRProvider):
    def __init__(
        self,
        *,
        name: str = "faster_whisper",
        model: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        beam_size: int = 5,
        vad_filter: bool = True,
        language: str | None = None,
        engine_factory: EngineFactory = load_whisper,
    ) -> None:
        self.name = name
        self.model = model
        self.is_cloud = False
        self.device = device
        self.compute_type = compute_type
        self.beam_size = beam_size
        self.vad_filter = vad_filter
        self.language = language
        self._engine_factory = engine_factory
        self._engine: Any | None = None
        self._lock = threading.Lock()

    @classmethod
    def from_config(cls, config: ProviderConfig, http: HttpClient | None = None) -> Self:
        options = config.options
        return cls(
            name=config.provider,
            model=config.model or default_asr_model(config.provider) or "small",
            device=str(options.get("device", "cpu")),
            compute_type=str(options.get("compute_type", "int8")),
            beam_size=int(options.get("beam_size", 5)),
            vad_filter=bool(options.get("vad_filter", True)),
            language=options.get("language") or None,
        )

    def _transcribe(
        self, audio: Path, *, language: str | None, progress: Progress | None
    ) -> tuple[Sequence[ASRSegment], str, float]:
        with self._lock:
            if self._engine is None:
                self._engine = self._engine_factory(self.model, self.device, self.compute_type)
            try:
                pieces, info = self._engine.transcribe(
                    str(audio),
                    language=language,
                    beam_size=self.beam_size,
                    word_timestamps=True,
                    vad_filter=self.vad_filter,
                )
                segments = []
                for piece in pieces:  # a generator: decoding happens while iterating
                    segments.append(_segment(piece))
                    if progress is not None:
                        progress(float(piece.end), float(info.duration))
            except (OSError, RuntimeError, ValueError) as exc:
                raise ProviderError(f"faster-whisper không nhận dạng được {audio.name}: {exc}") from exc
        return segments, str(info.language), float(info.duration)


def _segment(piece: Any) -> ASRSegment:
    words = tuple(
        ASRWord(text=w.word, t_start=max(0.0, float(w.start)), t_end=max(0.0, float(w.end)), probability=w.probability)
        for w in piece.words or ()
    )
    return ASRSegment(
        text=str(piece.text).strip(),
        t_start=max(0.0, float(piece.start)),
        t_end=max(0.0, float(piece.end)),
        words=words,
    )
