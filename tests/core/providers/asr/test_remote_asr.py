"""spec 03 FR-07c / AC-17 — ASR provider ``remote``: Whisper on the team's inference server.

The server is a ``httpx.MockTransport`` (constitution art. 6: no network in tests).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from mentormind.core.config import Settings
from mentormind.core.guard import ConfidentialDataError
from mentormind.core.providers.asr import ASRSegment, ASRWord, get_asr_provider
from mentormind.core.providers.asr.backends.remote import SERVER_DEFAULT_MODEL, RemoteASR
from mentormind.core.providers.errors import ProviderConfigError, ProviderError
from mentormind.core.schemas.common import DataClassification
from tests.core.providers.inference.fakes import PRIVATE_URL, PUBLIC_URL, FakeInferenceServer, multipart

CONFIDENTIAL = DataClassification.FACTORY_CONFIDENTIAL

VERBOSE_JSON: dict[str, Any] = {
    "text": "ครับ วางถ้วย",
    "language": "th",
    "duration": 12.5,
    "segments": [
        {
            "id": 0,
            "start": 0.4,
            "end": 1.6,
            "text": " ครับ วางถ้วย",
            "words": [
                {"word": " คร", "start": 0.4, "end": 0.7, "probability": 0.9},
                {"word": "ับ", "start": 0.7, "end": 1.0, "probability": 0.95},
                {"word": " วางถ้วย", "start": 1.0, "end": 1.6, "probability": None},
            ],
        },
        {"id": 1, "start": 3.0, "end": 4.0, "text": " ok.", "words": [{"word": " ok.", "start": 3.0, "end": 4.0}]},
    ],
    "words": [],
}


def audio_file(tmp_path: Path) -> Path:
    path = tmp_path / "expert.wav"
    path.write_bytes(b"RIFF....WAVE")
    return path


def test_ac_17_remote_maps_the_verbose_json_answer_exactly(tmp_path: Path) -> None:
    server = FakeInferenceServer({"/audio/transcriptions": VERBOSE_JSON})
    asr = RemoteASR(server.client(api_key="tok"))
    heard: list[tuple[float, float]] = []
    result = asr.transcribe(
        audio_file(tmp_path), classification=CONFIDENTIAL, progress=lambda done, total: heard.append((done, total))
    )
    first, second = result.segments
    assert first == ASRSegment(
        text="ครับ วางถ้วย",
        t_start=0.4,
        t_end=1.6,
        words=(
            ASRWord(text=" คร", t_start=0.4, t_end=0.7, probability=0.9),  # raw token, leading space kept
            ASRWord(text="ับ", t_start=0.7, t_end=1.0, probability=0.95),
            ASRWord(text=" วางถ้วย", t_start=1.0, t_end=1.6, probability=None),
        ),
    )
    assert second.text == "ok." and [w.text for w in second.words] == [" ok."]
    assert (result.language, result.duration_s, result.provider, result.model) == (
        "th",
        12.5,
        "remote",
        "server-default",
    )
    assert heard == [(12.5, 12.5)]  # one answer for the whole file: progress once, at the end
    [request] = server.requests
    assert (
        str(request.url) == f"{PRIVATE_URL}/audio/transcriptions" and request.headers["Authorization"] == "Bearer tok"
    )
    fields, files = multipart(request)
    assert files == {"file": ("expert.wav", b"RIFF....WAVE")}
    # Language detected per file (no ``language``), the server's own model (no ``model``).
    assert fields == {"response_format": ["verbose_json"], "timestamp_granularities[]": ["word"]}


def test_ac_17_a_forced_language_and_a_configured_model_are_sent(tmp_path: Path) -> None:
    server = FakeInferenceServer({"/audio/transcriptions": {**VERBOSE_JSON, "language": "vi"}})
    asr = RemoteASR(server.client(), model="large-v3", language="vi")
    assert asr.transcribe(audio_file(tmp_path), classification="public").model == "large-v3"
    fields, _ = multipart(server.requests[0])
    assert fields["language"] == ["vi"] and fields["model"] == ["large-v3"]


def test_ac_17_words_listed_only_at_the_top_level_go_to_their_segment(tmp_path: Path) -> None:
    body = {
        "language": "vi",
        "duration": 5.0,
        "segments": [{"start": 0.0, "end": 2.0, "text": "Đặt cốc."}, {"start": 2.0, "end": 4.0, "text": "Xong."}],
        "words": [
            {"word": " Đặt", "start": 0.1, "end": 0.5},
            {"word": " cốc.", "start": 0.5, "end": 1.0},
            {"word": " Xong.", "start": 2.2, "end": 2.8},
        ],
    }
    server = FakeInferenceServer({"/audio/transcriptions": body})
    result = RemoteASR(server.client()).transcribe(audio_file(tmp_path), classification="public")
    assert [[w.text for w in s.words] for s in result.segments] == [[" Đặt", " cốc."], [" Xong."]]


def test_ac_17_cloud_url_refuses_factory_speech_before_any_request(tmp_path: Path) -> None:
    server = FakeInferenceServer({"/audio/transcriptions": VERBOSE_JSON})
    cloud = RemoteASR(server.client(PUBLIC_URL))
    assert cloud.is_cloud is True
    with pytest.raises(ConfidentialDataError):
        cloud.transcribe(tmp_path / "never-opened.wav", classification=CONFIDENTIAL)
    assert server.requests == []
    declared = RemoteASR(server.client(PUBLIC_URL, local_hosts=["inference.example.com"]))
    assert declared.transcribe(audio_file(tmp_path), classification=CONFIDENTIAL).segments


def test_ac_17_settings_select_remote_and_a_missing_url_names_the_variable(tmp_path: Path) -> None:
    with pytest.raises(ProviderConfigError, match="KNOWHOW_INFERENCE_URL"):
        get_asr_provider(Settings(_env_file=None, asr_provider="remote", inference_url=None))
    settings = Settings(
        _env_file=None,
        asr_provider="remote",
        inference_url=PUBLIC_URL,
        vlm_base_url="https://inference.example.com/ollama/v1",  # the VLM is that same server
        vlm_api_key=SecretStr("same-server"),
        asr_language="th",
    )
    provider = get_asr_provider(settings)
    assert isinstance(provider, RemoteASR) and provider.is_cloud is True and provider.language == "th"
    assert provider.model == SERVER_DEFAULT_MODEL and provider.where == "server"
    assert provider._client.endpoint.api_key == "same-server"  # KNOWHOW_INFERENCE_API_KEY empty -> VLM key, same host
    assert provider._client.endpoint.timeout_s == settings.inference_timeout_s == 1800


def test_a_malformed_answer_is_a_provider_error(tmp_path: Path) -> None:
    server = FakeInferenceServer({"/audio/transcriptions": {"segments": [{"text": "x"}]}})
    with pytest.raises(ProviderError, match="verbose_json"):
        RemoteASR(server.client()).transcribe(audio_file(tmp_path), classification="public")
