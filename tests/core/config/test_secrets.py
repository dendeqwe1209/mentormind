"""Secret lookup: process environment first, then the repo's .env (spec 01 FR-09)."""

from __future__ import annotations

from pathlib import Path

from mentormind.core.config import lookup_secret


def test_secret_lookup_prefers_process_env(tmp_path: Path) -> None:
    secrets = tmp_path / "secrets.env"
    secrets.write_text("OPENROUTER_API_KEY=from-file\n", encoding="utf-8")
    env = {"OPENROUTER_API_KEY": "from-env"}
    assert lookup_secret("OPENROUTER_API_KEY", secrets_file=secrets, environ=env) == "from-env"


def test_secret_lookup_falls_back_to_secrets_file(tmp_path: Path) -> None:
    secrets = tmp_path / "secrets.env"
    secrets.write_text("# comment\nOPENROUTER_API_KEY = sk-or-123 \n", encoding="utf-8")
    assert lookup_secret("OPENROUTER_API_KEY", secrets_file=secrets, environ={}) == "sk-or-123"


def test_secret_lookup_treats_blank_as_missing(tmp_path: Path) -> None:
    secrets = tmp_path / "secrets.env"
    secrets.write_text("OPENROUTER_API_KEY=\n", encoding="utf-8")
    assert lookup_secret("OPENROUTER_API_KEY", secrets_file=secrets, environ={}) is None
    assert lookup_secret("X", secrets_file=tmp_path / "missing.env", environ={}) is None
