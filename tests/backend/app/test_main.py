"""spec 01 FR-01/FR-03 for the API: one Settings for the whole repo, no requirements.txt."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from mentormind.backend.app import main
from mentormind.core.config import Settings

REPO = Path(__file__).resolve().parents[3]


def test_fr_03_api_reads_the_core_settings() -> None:
    defaults = Settings(_env_file=None)
    assert defaults.cors_origins == ["http://localhost:5173"]
    assert main.get_settings.__module__ == "mentormind.core.config.settings"


def test_fr_05_cors_only_for_the_configured_origin() -> None:
    client = TestClient(main.app)
    origin = main.settings.cors_origins[0]
    allowed = client.get("/health", headers={"Origin": origin})
    assert allowed.json() == {"status": "ok"}
    assert allowed.headers["access-control-allow-origin"] == origin
    other = client.get("/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in other.headers


def test_fr_01_backend_has_no_requirements_file() -> None:
    assert not (REPO / "mentormind" / "backend" / "requirements.txt").exists()
    assert not (REPO / "mentormind" / "backend" / "app" / "config.py").exists()
