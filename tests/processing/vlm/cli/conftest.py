"""Every ``knowhow vlm`` CLI test runs in its own folder with fake providers and a file sink."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from mentormind.core.config import get_settings


@pytest.fixture(autouse=True)
def _hermetic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.chdir(tmp_path)
    for name, value in {
        "KNOWHOW_VLM_PROVIDER": "fake",
        "KNOWHOW_LLM_PROVIDER": "fake",
        "KNOWHOW_GUARD_AUDIT_DIR": str(tmp_path / "audit"),
        "KNOWHOW_PROFILE_SINK": "file",
        "DASHSCOPE_API_KEY": "sk-test",
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
