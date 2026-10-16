"""spec 03 FR-07c / AC-09 — ASR providers: guard before the audio is read, registry, one model per process.

No model is downloaded: faster-whisper's engine is a stand-in with the same ``transcribe`` surface.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from mentormind.core.config import Settings
from mentormind.core.guard import ConfidentialDataError
from mentormind.core.providers.asr import ASR_REGISTRY, ASRSegment, get_asr_provider
from mentormind.core.providers.asr.backends.fake import FakeASR
from mentormind.core.providers.asr.backends.faster_whisper import FasterWhisperASR, load_whisper
from mentormind.core.providers.errors import ProviderConfigError, ProviderError
from mentormind.core.schemas.common import DataClassification

CONFIDENTIAL = DataClassification.FACTORY_CONFIDENTIAL


def audio_file(tmp_path: Path) -> Path:
    path = tmp_path / "expert.wav"
    path.write_bytes(b"RIFF....WAVE")
    return path


def test_ac_09_cloud_asr_refuses_factory_speech_before_reading_the_file(tmp_path: Path) -> None:
    cloud = FakeASR([{"text": "x", "t_start": 0, "t_end": 1}], is_cloud=True)
    with pytest.raises(ConfidentialDataError):
        cloud.transcribe(tmp_path / "never-opened.wav", classification=CONFIDENTIAL)
    assert cloud.calls == []  # the engine was never reached
    local = FakeASR([{"text": "Đặt cốc nghiêng.", "t_start": 0.5, "t_end": 2.0}])
    result = local.transcribe(audio_file(tmp_path), classification=CONFIDENTIAL)
    assert [s.text for s in result.segments] == ["Đặt cốc nghiêng."]
    assert (result.provider, result.language, result.duration_s) == ("fake", "vi", 2.0)


def test_ac_09_unknown_provider_lists_the_registered_ones(tmp_path: Path) -> None:
    with pytest.raises(ProviderConfigError) as exc:
        get_asr_provider(Settings(_env_file=None, asr_provider="openai_whisper_api"))
    assert "faster_whisper" in str(exc.value) and "fake" in str(exc.value)
    # spec 03 FR-07: no third-party ASR — here, or the team's own inference server (remote).
    assert set(ASR_REGISTRY.names()) == {"fake", "faster_whisper", "remote"}


def test_ac_09_one_provider_per_configuration_so_the_model_loads_once(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, asr_provider="faster_whisper", asr_model="tiny")
    first, second = get_asr_provider(settings), get_asr_provider(settings)
    assert first is second and isinstance(first, FasterWhisperASR)
    assert first.is_cloud is False and (first.device, first.compute_type, first.model) == ("cpu", "int8", "tiny")
    assert first.language is None  # spec 03 FR-07c: detected per file unless KNOWHOW_ASR_LANGUAGE forces one
    forced = get_asr_provider(
        Settings(_env_file=None, asr_provider="faster_whisper", asr_model="tiny", asr_language="vi")
    )
    assert forced.language == "vi" and forced is not first
    assert get_asr_provider(Settings(_env_file=None, asr_provider="faster_whisper", asr_model="base")) is not first

    loads: list[tuple[str, str, str]] = []

    def factory(model: str, device: str, compute_type: str) -> Any:
        loads.append((model, device, compute_type))
        return FakeEngine()

    provider = FasterWhisperASR(model="tiny", engine_factory=factory)
    for _ in range(2):
        provider.transcribe(audio_file(tmp_path), classification="public")
    assert loads == [("tiny", "cpu", "int8")]


class FakeEngine:
    """faster-whisper's ``WhisperModel.transcribe`` surface: a lazy generator plus info."""

    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    def transcribe(self, audio: str, **kwargs: Any) -> tuple[Any, Any]:
        self.kwargs = kwargs
        words = [
            SimpleNamespace(word=" Đặt", start=0.4, end=0.7, probability=0.9),
            SimpleNamespace(word=" cốc", start=0.7, end=1.0, probability=0.95),
            SimpleNamespace(word=" nghiêng.", start=1.0, end=1.6, probability=0.8),
        ]
        piece = SimpleNamespace(text=" Đặt cốc nghiêng.", start=0.4, end=1.6, words=words)
        return iter([piece]), SimpleNamespace(language="vi", duration=12.0)


def test_faster_whisper_keeps_word_timestamps_and_reports_progress(tmp_path: Path) -> None:
    engine = FakeEngine()
    provider = FasterWhisperASR(model="tiny", engine_factory=lambda *a: engine, beam_size=3)
    heard: list[tuple[float, float]] = []
    result = provider.transcribe(
        audio_file(tmp_path), classification="public", progress=lambda done, total: heard.append((done, total))
    )
    [segment] = result.segments
    assert isinstance(segment, ASRSegment) and segment.text == "Đặt cốc nghiêng."
    assert [(w.text, w.t_start) for w in segment.words] == [(" Đặt", 0.4), (" cốc", 0.7), (" nghiêng.", 1.0)]
    assert engine.kwargs == {"language": None, "beam_size": 3, "word_timestamps": True, "vad_filter": True}
    assert heard == [(1.6, 12.0)] and result.duration_s == 12.0


def test_engine_failures_and_missing_files_are_provider_errors(tmp_path: Path) -> None:
    class Broken:
        def transcribe(self, audio: str, **kwargs: Any) -> Any:
            raise RuntimeError("bad audio")

    provider = FasterWhisperASR(engine_factory=lambda *a: Broken())
    with pytest.raises(ProviderError, match="bad audio"):
        provider.transcribe(audio_file(tmp_path), classification="public")
    with pytest.raises(ProviderError, match="Không thấy"):
        provider.transcribe(tmp_path / "missing.wav", classification="public")


def test_without_faster_whisper_installed_the_error_says_how(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "faster_whisper", None)  # import fails
    with pytest.raises(ProviderConfigError, match="--extra video"):
        load_whisper("small", "cpu", "int8")
