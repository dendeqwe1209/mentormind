from __future__ import annotations

from pathlib import Path

import pytest

from mentormind.core.config import Settings
from tests.core.providers.fakes import RecordingHttp


@pytest.fixture
def http() -> RecordingHttp:
    return RecordingHttp()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Hermetic settings: no .env, an empty secrets file, no inherited KNOWHOW_* values."""
    secrets = tmp_path / "secrets.env"
    secrets.write_text("", encoding="utf-8")
    return Settings(
        _env_file=None,
        vlm_provider="local_openai",
        vlm_base_url=None,
        vlm_model=None,
        vlm_api_key=None,
        secrets_file=secrets,
        guard_audit_dir=tmp_path / "audit",
        guard_blur_faces=False,  # face tests inject a fake detector; never download in tests
        guard_face_model=tmp_path / "no-model.onnx",
    )
