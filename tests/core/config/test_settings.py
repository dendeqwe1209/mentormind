"""spec 01 FR-03 — settings come from KNOWHOW_* variables and .env files."""

from __future__ import annotations

import pytest

from mentormind.core.config import Settings


def test_fr_03_settings_read_prefixed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOWHOW_VLM_PROVIDER", "openrouter")
    monkeypatch.setenv("KNOWHOW_VLM_MAX_FRAMES", "12")
    settings = Settings(_env_file=None)
    assert settings.vlm_provider == "openrouter"
    assert settings.vlm_max_frames == 12


def test_settings_defaults_target_the_self_hosted_vlm(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("KNOWHOW_VLM_PROVIDER", "KNOWHOW_VLM_FPS", "KNOWHOW_VLM_MAX_FRAMES"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    assert settings.vlm_provider == "local_openai"
    assert settings.vlm_fps == 4
    assert settings.vlm_max_frames == 48


def test_env_example_parses_into_settings() -> None:
    """Every value in .env.example is readable (e.g. a blank number is not); the values are free."""
    from mentormind.core.config import REPO_ROOT

    Settings(_env_file=REPO_ROOT / ".env.example")


def test_fr_09_api_keys_live_in_the_same_env_file_as_the_settings() -> None:
    """One dotenv file for everything: .env, never .secrets/ (which is documentation only)."""
    from mentormind.core.config import ENV_FILE, REPO_ROOT, lookup_secret

    assert ENV_FILE == REPO_ROOT / ".env"
    assert Settings.model_config["env_file"] == (ENV_FILE,)
    assert Settings(_env_file=None).secrets_file == ENV_FILE
    example = REPO_ROOT / ".env.example"
    for name in ("OPENROUTER_API_KEY", "DASHSCOPE_API_KEY", "VLM_SERVER_API_KEY"):
        assert f"\n{name}=" in example.read_text(), name
    # A vendor key set in that file is what the provider factories look up.
    assert lookup_secret("DASHSCOPE_API_KEY", secrets_file=example, environ={}) is None
