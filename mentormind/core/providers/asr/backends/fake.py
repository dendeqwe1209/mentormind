"""FakeASR — scripted speech for tests and offline demos; records every file it was given."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Self

from mentormind.core.providers.asr.base import ASRProvider, Progress
from mentormind.core.providers.asr.models import ASRSegment
from mentormind.core.providers.asr.registry import register_asr
from mentormind.core.providers.models import ProviderConfig
from mentormind.core.providers.transport import HttpClient


@register_asr("fake")
class FakeASR(ASRProvider):
    def __init__(
        self,
        segments: Sequence[ASRSegment | Mapping[str, Any]] = (),
        *,
        name: str = "fake",
        model: str = "fake-asr",
        is_cloud: bool = False,
        language: str | None = None,
        duration_s: float | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self.is_cloud = is_cloud
        self.language = language
        self._segments = [s if isinstance(s, ASRSegment) else ASRSegment.model_validate(s) for s in segments]
        self._duration = duration_s
        #: Audio files ``transcribe`` actually reached (after the guard).
        self.calls: list[Path] = []

    @classmethod
    def from_config(cls, config: ProviderConfig, http: HttpClient | None = None) -> Self:
        options = config.options
        return cls(
            list(options.get("segments", [])),
            name=config.provider,
            model=config.model or "fake-asr",
            is_cloud=bool(options.get("is_cloud", False)),
            language=options.get("language") or None,
        )

    def _transcribe(
        self, audio: Path, *, language: str | None, progress: Progress | None
    ) -> tuple[Sequence[ASRSegment], str, float]:
        self.calls.append(audio)
        duration = self._duration if self._duration is not None else max((s.t_end for s in self._segments), default=0.0)
        for segment in self._segments:
            if progress is not None:
                progress(segment.t_end, duration)
        return list(self._segments), language or "vi", duration  # a fake "detects" Vietnamese
