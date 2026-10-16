"""``remote`` — Whisper on the team's inference server (``KNOWHOW_INFERENCE_URL``, spec 03 FR-07c).

``POST {base}/audio/transcriptions`` (multipart ``file`` + ``response_format=verbose_json`` +
``timestamp_granularities[]=word``; ``language`` only when one is forced; ``model`` only when
``KNOWHOW_ASR_MODEL`` is set, else the server's default). The answer is mapped exactly like the local
engine's: segment text stripped, every word's raw text kept (leading space included: spec 03 FR-07
joins tokens on Whisper's own spacing). Local or cloud follows the URL; the base class runs
``DataGuard`` before the audio is opened.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, ClassVar, Self

from mentormind.core.providers.asr.base import ASRProvider, Progress
from mentormind.core.providers.asr.models import ASRSegment, ASRWord
from mentormind.core.providers.asr.registry import register_asr
from mentormind.core.providers.errors import ProviderError
from mentormind.core.providers.inference import InferenceClient, InferenceEndpoint
from mentormind.core.providers.models import ProviderConfig
from mentormind.core.providers.transport import HttpClient

#: What the transcript's provenance says when the server picked the model itself.
SERVER_DEFAULT_MODEL = "server-default"
TRANSCRIPTIONS_PATH = "/audio/transcriptions"


@register_asr("remote")
class RemoteASR(ASRProvider):
    where: ClassVar[str] = "server"

    def __init__(
        self,
        client: InferenceClient,
        *,
        name: str = "remote",
        model: str | None = None,
        language: str | None = None,
    ) -> None:
        self.name = name
        self.model = model or SERVER_DEFAULT_MODEL
        self.is_cloud = client.is_cloud
        self.language = language
        self._client = client
        self._send_model = model is not None

    @classmethod
    def from_config(cls, config: ProviderConfig, http: HttpClient | None = None) -> Self:
        """Raises: ProviderConfigError: no ``KNOWHOW_INFERENCE_URL``."""
        endpoint = InferenceEndpoint.resolve(
            config.base_url,
            api_key=config.api_key,
            local_hosts=config.local_hosts,
            timeout_s=config.timeout_s,
            max_retries=config.max_retries,
        )
        return cls(
            InferenceClient(endpoint),
            name=config.provider,
            model=config.model or None,
            language=config.options.get("language") or None,
        )

    def _transcribe(
        self, audio: Path, *, language: str | None, progress: Progress | None
    ) -> tuple[Sequence[ASRSegment], str, float]:
        form: dict[str, str | list[str]] = {
            "response_format": "verbose_json",
            "timestamp_granularities[]": "word",
        }
        if language:
            form["language"] = language
        if self._send_model:
            form["model"] = self.model
        body = self._client.post_file(TRANSCRIPTIONS_PATH, audio, data=form)
        segments, duration = parse_transcription(body)
        if progress is not None:  # one answer for the whole file: progress jumps to the end
            progress(duration, duration)
        return segments, str(body.get("language") or language or "und"), duration


def parse_transcription(body: Mapping[str, Any]) -> tuple[list[ASRSegment], float]:
    """Segments (with words) and audio length of a ``verbose_json`` answer.

    Words come from each segment; a server that lists them only at the top level (as OpenAI's
    API does) gets them assigned to the segment their start falls in.

    Raises:
        ProviderError: the answer does not have the ``verbose_json`` shape.
    """
    try:
        loose = [_word(w) for w in body.get("words") or ()]
        segments = []
        for raw in body.get("segments") or ():
            start, end = _time(raw["start"]), _time(raw["end"])
            words = tuple(_word(w) for w in raw.get("words") or ()) or tuple(
                w for w in loose if start <= w.t_start < end
            )
            segments.append(ASRSegment(text=str(raw["text"]).strip(), t_start=start, t_end=end, words=words))
        duration = body.get("duration")
        length = _time(duration) if duration is not None else max((s.t_end for s in segments), default=0.0)
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderError(f"Máy chủ ASR trả lời sai dạng verbose_json: {str(body)[:300]}") from exc
    return segments, length


def _word(raw: Mapping[str, Any]) -> ASRWord:
    probability = raw.get("probability")
    return ASRWord(
        text=str(raw["word"]),
        t_start=_time(raw["start"]),
        t_end=_time(raw["end"]),
        probability=None if probability is None else float(probability),
    )


def _time(value: Any) -> float:
    return max(0.0, float(value))
