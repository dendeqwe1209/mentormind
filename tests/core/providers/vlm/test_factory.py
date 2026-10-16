"""spec 04 FR-01, AC-11, AC-12 — building VLM providers from settings and secrets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from mentormind.core.config import Settings
from mentormind.core.providers.errors import ProviderConfigError
from mentormind.core.providers.openai_compat import OPENAI_COMPAT_ENDPOINTS
from mentormind.core.providers.vlm import VLM_REGISTRY, get_vlm_provider
from mentormind.core.providers.vlm.backends.openai_compat import OpenAICompatVLM
from mentormind.core.providers.vlm.catalog import DEFAULT_VLM_MODELS
from tests.core.providers.fakes import RecordingHttp


def with_provider(settings: Settings, **update: Any) -> Settings:
    return settings.model_copy(update=update)


def test_fr_01_spec_provider_names_are_registered() -> None:
    assert {"qwen_api", "local_openai", "fake"} <= set(VLM_REGISTRY.names())


def test_fr_01_every_vendor_row_is_registered_with_a_default_model() -> None:
    for name in OPENAI_COMPAT_ENDPOINTS:
        assert VLM_REGISTRY[name] is OpenAICompatVLM
        assert DEFAULT_VLM_MODELS.get(name), f"no default Qwen3-VL-8B model id for {name}"


def test_ac_11_unknown_provider_lists_known_names(settings: Settings) -> None:
    with pytest.raises(ProviderConfigError, match="local_openai"):
        get_vlm_provider(with_provider(settings, vlm_provider="nope"))


def test_ac_12_cloud_provider_without_key_explains_where_to_put_it(settings: Settings) -> None:
    with pytest.raises(ProviderConfigError, match=r"OPENROUTER_API_KEY.*\.secrets/README\.md"):
        get_vlm_provider(with_provider(settings, vlm_provider="openrouter"))


def test_ac_12_vendor_key_found_in_secrets_file(settings: Settings, http: RecordingHttp, frames: list[Path]) -> None:
    settings.secrets_file.write_text("SILICONFLOW_API_KEY=sk-sf-42\n", encoding="utf-8")
    vlm = get_vlm_provider(with_provider(settings, vlm_provider="siliconflow"), http=http)
    vlm.generate(frames, "p", classification="public")
    assert http.posts[0][2]["Authorization"] == "Bearer sk-sf-42"


def test_ac_12_explicit_knowhow_key_wins(settings: Settings, http: RecordingHttp) -> None:
    settings.secrets_file.write_text("OPENROUTER_API_KEY=from-file\n", encoding="utf-8")
    settings = with_provider(settings, vlm_provider="openrouter", vlm_api_key=SecretStr("mine"))
    vlm = get_vlm_provider(settings, http=http)
    vlm.generate([], "p", classification="public")
    assert http.posts[0][2]["Authorization"] == "Bearer mine"


def test_local_server_needs_no_key(settings: Settings, http: RecordingHttp, frames: list[Path]) -> None:
    vlm = get_vlm_provider(settings, http=http)
    vlm.generate(frames, "p", classification="synthetic")
    assert "Authorization" not in http.posts[0][2]


def test_generic_openai_compatible_needs_base_url(settings: Settings) -> None:
    generic = with_provider(settings, vlm_provider="openai_compatible", vlm_model="m")
    with pytest.raises(ProviderConfigError, match="KNOWHOW_VLM_BASE_URL"):
        get_vlm_provider(generic)


def test_extra_body_is_merged_but_never_overrides_the_call(settings: Settings, http: RecordingHttp) -> None:
    extra = {"presence_penalty": 1.5, "temperature": 0.9, "model": "hijack"}
    vlm = get_vlm_provider(with_provider(settings, vlm_extra_body=extra), http=http)
    vlm.generate([], "p", classification="public", temperature=0.2)
    payload = http.posts[0][1]
    assert payload["presence_penalty"] == 1.5
    assert payload["temperature"] == 0.2
    assert payload["model"] == "qwen3-vl:8b"


def test_ac_12_blank_knowhow_key_falls_back_to_vendor_key(settings: Settings, http: RecordingHttp) -> None:
    settings.secrets_file.write_text("OPENROUTER_API_KEY=sk-or-file\n", encoding="utf-8")
    blank = with_provider(settings, vlm_provider="openrouter", vlm_api_key=SecretStr(""))
    get_vlm_provider(blank, http=http).generate([], "p", classification="public")
    assert http.posts[0][2]["Authorization"] == "Bearer sk-or-file"


def test_dashscope_workspace_host_comes_from_the_secrets_file(settings: Settings, http: RecordingHttp) -> None:
    host = "https://ws-123.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
    settings.secrets_file.write_text(f"DASHSCOPE_API_KEY=sk-ws-1\nDASHSCOPE_BASE_URL={host}\n", encoding="utf-8")
    vlm = get_vlm_provider(settings.model_copy(update={"vlm_provider": "qwen_api"}), http=http)
    vlm.generate([], "p", classification="public")
    assert http.posts[0][0] == f"{host}/chat/completions"
    assert vlm.is_cloud
