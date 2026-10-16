"""ASR provider interface (spec 03 FR-07c).

:meth:`ASRProvider.transcribe` is a template method, so no provider can skip the guard:

1. ``DataGuard.check`` — confidential speech never reaches a cloud provider, checked BEFORE the
   audio file is opened (constitution art. 2). Spec 03 FR-07 forbids third-party ASR: backends run
   here or on the team's inference server (``remote``), which is cloud when its URL is public;
2. the subclass's :meth:`ASRProvider._transcribe` runs the engine.
"""

from __future__ import annotations

import time
from abc import abstractmethod
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import ClassVar

from mentormind.core.guard import DataGuard
from mentormind.core.providers.asr.models import ASRResult, ASRSegment
from mentormind.core.providers.base import ProviderBase
from mentormind.core.providers.errors import ProviderError
from mentormind.core.schemas.common import DataClassification

#: ``progress(seconds_heard, audio_seconds)``, called as the engine moves through the audio.
Progress = Callable[[float, float], None]


class ASRProvider(ProviderBase):
    """Turns the speech of an audio file into timed text. Subclass, then ``@register_asr("name")``."""

    kind: ClassVar[str] = "ASR"
    #: Where the engine runs, for ``knowhow video providers``: "local" or "server".
    where: ClassVar[str] = "local"

    #: Model id the engine runs (goes into the transcript's provenance).
    model: str
    #: Language when a call names none (``KNOWHOW_ASR_LANGUAGE``); None = detected per file.
    language: str | None = None

    def transcribe(
        self,
        audio: Path,
        *,
        classification: DataClassification | str,
        language: str | None = None,
        progress: Progress | None = None,
    ) -> ASRResult:
        """Recognise the speech of ``audio`` (any format the engine reads; spec 03 hands it WAV).

        Raises:
            ConfidentialDataError: ``classification`` may not go to this provider — raised before
                the file is opened.
            ProviderError: the file is missing, or the engine failed.
        """
        DataGuard.check(classification, self)
        if not audio.is_file():
            raise ProviderError(f"Không thấy file audio {audio}")
        started = time.perf_counter()
        segments, used_language, duration = self._transcribe(
            audio, language=language or self.language, progress=progress
        )
        return ASRResult(
            segments=tuple(segments),
            language=used_language,
            duration_s=duration,
            latency_s=time.perf_counter() - started,
            provider=self.name,
            model=self.model,
        )

    @abstractmethod
    def _transcribe(
        self, audio: Path, *, language: str | None, progress: Progress | None
    ) -> tuple[Sequence[ASRSegment], str, float]:
        """Run the engine once: its segments (with word timestamps), the language, the audio length."""
