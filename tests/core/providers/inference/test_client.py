"""spec 02 FR-02c/FR-07d, spec 03 FR-07c — the team's inference server: locality, auth, uploads."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from mentormind.core.config import Settings
from mentormind.core.providers.errors import ProviderConfigError, ProviderError
from mentormind.core.providers.inference import InferenceClient, InferenceEndpoint
from tests.core.providers.inference.fakes import PRIVATE_URL, PUBLIC_URL, FakeInferenceServer, multipart


def test_missing_url_names_the_variable_to_set() -> None:
    for url in (None, "", "  "):
        with pytest.raises(ProviderConfigError, match="KNOWHOW_INFERENCE_URL"):
            InferenceEndpoint.resolve(url)
    with pytest.raises(ProviderConfigError, match="KNOWHOW_INFERENCE_URL"):
        InferenceClient.from_settings(Settings(_env_file=None, inference_url=None))


def test_locality_is_judged_from_the_url_like_the_vlm() -> None:
    assert InferenceEndpoint.resolve(PRIVATE_URL).is_cloud is False
    assert InferenceEndpoint.resolve("http://gpu-box:8000/v1").is_cloud is False  # LAN hostname
    assert InferenceEndpoint.resolve(PUBLIC_URL).is_cloud is True
    declared = InferenceEndpoint.resolve(PUBLIC_URL, local_hosts=["inference.example.com"])
    assert declared.is_cloud is False


def test_ac_19_the_key_falls_back_to_the_vlm_key_of_the_same_host_only() -> None:
    def endpoint(vlm_base_url: str | None = "http://10.0.0.5:11434/v1", **values: Any) -> InferenceEndpoint:
        settings = Settings(_env_file=None, inference_url=PRIVATE_URL, vlm_base_url=vlm_base_url, **values)
        return InferenceEndpoint.from_settings(settings)

    assert endpoint(inference_api_key=SecretStr("inf"), vlm_api_key=SecretStr("vlm")).api_key == "inf"
    assert endpoint(inference_api_key=SecretStr(" "), vlm_api_key=SecretStr("vlm")).api_key == "vlm"
    assert endpoint(inference_api_key=None, vlm_api_key=None).api_key is None
    # A cloud vendor's key forced in KNOWHOW_VLM_API_KEY never goes to another server.
    vendor = {"vlm_provider": "qwen_api", "vlm_api_key": SecretStr("sk-vendor"), "inference_api_key": None}
    assert endpoint(vlm_base_url=None, **vendor).api_key is None
    assert endpoint(vlm_base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1", **vendor).api_key is None
    settings = Settings(_env_file=None, inference_url=PRIVATE_URL, inference_timeout_s=60, inference_max_retries=1)
    assert (InferenceEndpoint.from_settings(settings).timeout_s, settings.inference_max_retries) == (60, 1)
    assert Settings(_env_file=None).inference_timeout_s == 1800


def test_bearer_header_only_when_a_key_is_set() -> None:
    server = FakeInferenceServer({"/embeddings": {"data": []}})
    server.client(api_key="tok").post_json("/embeddings", {"input": []})
    server.client().post_json("embeddings", {"input": []})
    assert server.requests[0].headers["Authorization"] == "Bearer tok"
    assert "Authorization" not in server.requests[1].headers
    assert [str(r.url) for r in server.requests] == [f"{PRIVATE_URL}/embeddings"] * 2


def test_a_file_upload_is_multipart_and_reopened_on_retry(tmp_path: Path) -> None:
    replies = [httpx.Response(503), httpx.Response(200, json={"ok": True})]
    server = FakeInferenceServer({"/audio/transcriptions": lambda request: replies.pop(0)})
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF-bytes")
    endpoint = InferenceEndpoint.resolve(PRIVATE_URL, max_retries=1)
    client = InferenceClient(endpoint, transport=httpx.MockTransport(server.handle), sleep=lambda s: None)
    assert client.post_file("/audio/transcriptions", audio, data={"a": "1", "b[]": ["x", "y"]}) == {"ok": True}
    assert len(server.requests) == 2
    for request in server.requests:
        fields, files = multipart(request)
        assert files == {"file": ("a.wav", b"RIFF-bytes")} and fields == {"a": ["1"], "b[]": ["x", "y"]}


def test_ac_19_an_upload_that_got_no_answer_in_time_is_not_resent(tmp_path: Path) -> None:
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF-bytes")
    timeouts: list[dict[str, float]] = []

    def slow(request: httpx.Request) -> httpx.Response:
        timeouts.append(request.extensions["timeout"])
        raise httpx.ReadTimeout("no answer", request=request)

    def client(handler: Any) -> InferenceClient:
        endpoint = InferenceEndpoint.resolve(PRIVATE_URL, max_retries=2)
        return InferenceClient(endpoint, transport=httpx.MockTransport(handler), sleep=lambda s: None)

    with pytest.raises(ProviderError, match="not resent"):
        client(slow).post_file("/audio/transcriptions", audio)
    assert len(timeouts) == 1  # the server is still transcribing: a copy would only queue behind it
    assert timeouts[0]["connect"] == 10.0 and timeouts[0]["read"] == 1800.0  # unreachable = fails fast
    gateway: list[httpx.Request] = []

    def proxy_gave_up(request: httpx.Request) -> httpx.Response:
        gateway.append(request)
        return httpx.Response(504)

    with pytest.raises(ProviderError) as caught:
        client(proxy_gave_up).post_file("/documents/convert", audio)
    assert caught.value.status_code == 504 and len(gateway) == 1
    refused: list[httpx.Request] = []

    def unreachable(request: httpx.Request) -> httpx.Response:
        refused.append(request)
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ProviderError):
        client(unreachable).post_file("/audio/transcriptions", audio)
    assert len(refused) == 3  # nothing reached the server: retried


def test_errors_never_show_the_basic_auth_password(tmp_path: Path) -> None:
    server = FakeInferenceServer({"/documents/convert": httpx.Response(422, json={"error": "bad pdf"})})
    doc = tmp_path / "a.pdf"
    doc.write_bytes(b"%PDF")
    with pytest.raises(ProviderError) as caught:
        server.client(PUBLIC_URL).post_file("/documents/convert", doc)
    assert caught.value.status_code == 422 and "bad pdf" in str(caught.value) and "s3cret" not in str(caught.value)
    assert server.client(PUBLIC_URL).shown_url == "https://inference.example.com/v1"
    with pytest.raises(ProviderError, match="missing.pdf"):
        server.client().post_file("/documents/convert", tmp_path / "missing.pdf")
