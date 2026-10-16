"""spec 06 T06-1 — LLM providers: registry/factory, guard, confidential passages (AC-04)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr

from mentormind.core.config import Settings
from mentormind.core.guard import ConfidentialDataError, GuardPolicy
from mentormind.core.providers.errors import ProviderConfigError
from mentormind.core.providers.llm import (
    LLM_REGISTRY,
    ContextPassage,
    filter_passages,
    get_llm_provider,
    strictest,
)
from mentormind.core.providers.llm.backends.fake import FakeLLM
from mentormind.core.providers.openai_compat import OPENAI_COMPAT_ENDPOINTS
from mentormind.core.schemas.common import DataClassification
from tests.core.providers.fakes import RecordingHttp

PUBLIC = ContextPassage(ref_id="WP-PACK01-001", text="Đặt cốc vào thùng", classification="public")
SECRET = ContextPassage(
    ref_id="WP-LINE3-004", text="Chỉnh lực kẹp 12 N ở trạm 3", classification="factory_confidential"
)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    secrets = tmp_path / "secrets.env"
    secrets.write_text("", encoding="utf-8")
    return Settings(
        _env_file=None,
        llm_provider="local_openai",
        llm_model=None,
        llm_api_key=None,
        secrets_file=secrets,
        guard_audit_dir=tmp_path / "audit",
    )


def prompt_from(passages: list[ContextPassage]) -> str:
    return "Ngữ cảnh:\n" + "\n".join(f"[{p.ref_id}] {p.text}" for p in passages)


def test_ac_04_cloud_prompt_never_contains_confidential_passages() -> None:
    llm = FakeLLM(["ok"], name="qwen_api", is_cloud=True)
    llm.guard_policy = GuardPolicy(audit_dir=None)
    kept = filter_passages([PUBLIC, SECRET], llm)
    llm.generate(prompt_from(kept), classification=strictest(p.classification for p in kept))
    sent = llm.calls[0].prompt
    assert PUBLIC.text in sent
    assert SECRET.text not in sent and SECRET.ref_id not in sent


def test_ac_04_self_hosted_llm_keeps_every_passage() -> None:
    llm = FakeLLM(["ok"], name="local_openai", is_cloud=False)
    kept = filter_passages([PUBLIC, SECRET], llm)
    assert kept == [PUBLIC, SECRET]
    llm.generate(prompt_from(kept), classification=strictest(p.classification for p in kept))
    assert SECRET.text in llm.calls[0].prompt


def test_dataguard_still_blocks_confidential_prompts_to_the_cloud() -> None:
    llm = FakeLLM(name="openrouter", is_cloud=True)
    with pytest.raises(ConfidentialDataError):
        llm.generate(prompt_from([SECRET]), classification="factory_confidential")
    assert llm.calls == []


def test_strictest_label() -> None:
    labels = [DataClassification.PUBLIC, DataClassification.SYNTHETIC]
    assert strictest(labels) is DataClassification.SYNTHETIC
    assert strictest([]) is DataClassification.PUBLIC


def test_every_vendor_row_is_an_llm_provider_too() -> None:
    assert set(OPENAI_COMPAT_ENDPOINTS) | {"openai_compatible", "fake"} <= set(LLM_REGISTRY.names())


@pytest.mark.parametrize(
    ("provider", "key_env", "model"),
    [
        ("qwen_api", "DASHSCOPE_API_KEY", "qwen-plus"),
        ("openrouter", "OPENROUTER_API_KEY", "qwen/qwen-plus"),
    ],
)
def test_cloud_llm_defaults_and_key_from_secrets(settings: Settings, provider: str, key_env: str, model: str) -> None:
    settings.secrets_file.write_text(f"{key_env}=sk-test\n", encoding="utf-8")
    http = RecordingHttp(content="xin chào")
    llm = get_llm_provider(settings.model_copy(update={"llm_provider": provider}), http=http)
    assert llm.is_cloud and llm.model == model
    assert llm.generate_text("chào", classification="public") == "xin chào"
    _url, payload, headers = http.posts[0]
    assert payload["messages"][-1] == {"role": "user", "content": "chào"}
    assert headers["Authorization"] == "Bearer sk-test"


def test_local_llm_uses_the_self_hosted_server(settings: Settings) -> None:
    http = RecordingHttp(content="ok")
    llm = get_llm_provider(settings, http=http)
    assert (llm.name, llm.is_cloud, llm.model) == (
        "local_openai",
        False,
        "qwen3-vl:8b",
    )
    llm.generate("hỏi", classification="factory_confidential")
    assert http.posts[0][0] == "http://127.0.0.1:11434/v1/chat/completions"


def test_siliconflow_llm_needs_an_explicit_model(settings: Settings) -> None:
    update = {"llm_provider": "siliconflow", "llm_api_key": SecretStr("k")}
    with pytest.raises(ProviderConfigError, match="KNOWHOW_LLM_MODEL"):
        get_llm_provider(settings.model_copy(update=update))


def test_cloud_llm_prompt_is_masked_and_answer_restored(settings: Settings) -> None:
    http = RecordingHttp(content="Gọi [PHONE_1] để báo thiếu hàng")
    update = {"llm_provider": "qwen_api", "llm_api_key": SecretStr("k")}
    llm = get_llm_provider(settings.model_copy(update=update), http=http)
    answer = llm.generate_text("Tổ trưởng: 0987654321. Hỏi cách báo thiếu hàng.", classification="public")
    assert "0987654321" not in http.posts[0][1]["messages"][-1]["content"]
    assert answer == "Gọi 0987654321 để báo thiếu hàng"


def test_llm_is_the_vlm_when_no_llm_provider_is_set(settings: Settings) -> None:
    vlm = {
        "llm_provider": None,
        "vlm_provider": "local_openai",
        "vlm_base_url": "http://gpu-box:11434/v1",
        "vlm_model": "qwen3-vl:8b",
        "vlm_api_key": SecretStr("k"),
        "vlm_extra_body": {"presence_penalty": 1.5},
    }
    http = RecordingHttp(content="ok")
    llm = get_llm_provider(settings.model_copy(update=vlm), http=http)
    assert (llm.name, llm.model, llm.is_cloud) == ("local_openai", "qwen3-vl:8b", False)
    llm.generate("hỏi", classification="factory_confidential")
    url, payload, headers = http.posts[0]
    assert url == "http://gpu-box:11434/v1/chat/completions" and headers["Authorization"] == "Bearer k"
    # The LLM keeps its own knobs: no VLM sampling extras, its own max_tokens.
    assert payload["max_tokens"] == settings.llm_max_tokens and "presence_penalty" not in payload


def test_an_llm_setting_wins_over_the_vlm_it_follows(settings: Settings) -> None:
    update = {"llm_provider": None, "vlm_model": "qwen3-vl:8b", "llm_model": "qwen3:8b"}
    assert get_llm_provider(settings.model_copy(update=update), http=RecordingHttp()).model == "qwen3:8b"


def test_an_explicit_llm_provider_does_not_follow_the_vlm(settings: Settings) -> None:
    update = {"llm_provider": "qwen_api", "llm_api_key": SecretStr("k"), "vlm_model": "qwen3-vl:8b"}
    assert get_llm_provider(settings.model_copy(update=update), http=RecordingHttp()).model == "qwen-plus"


def test_default_settings_put_the_llm_on_the_self_hosted_vlm() -> None:
    settings = Settings(_env_file=None)
    assert settings.llm_provider is None and settings.vlm_provider == "local_openai"
