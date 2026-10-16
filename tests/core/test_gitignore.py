"""spec 01 AC-06 (+ FR-06) — raw media and secrets never enter git."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from mentormind.core.config import REPO_ROOT

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or not (REPO_ROOT / ".git").exists(), reason="needs a git checkout"
)


def is_ignored(path: str) -> bool:
    result = subprocess.run(["git", "check-ignore", "--no-index", "-q", path], cwd=REPO_ROOT, check=False)
    return result.returncode == 0


@pytest.mark.parametrize("path", ["data/raw/x.mp4", "data/factory/line3.mov", "clip.wav"])
def test_ac_06_raw_media_is_ignored(path: str) -> None:
    assert is_ignored(path)


def test_ac_06_samples_are_not_ignored() -> None:
    assert not is_ignored("data/samples/demo.mp4")


def test_public_demo_video_is_tracked_through_git_lfs() -> None:
    """data/video/ holds the public LASI demo video; LFS keeps the repo small (spec 04 §6)."""
    assert not is_ignored("data/video/demo.mkv")
    attributes = (REPO_ROOT / ".gitattributes").read_text()
    for suffix in ("mkv", "mp4", "mov", "webm"):
        assert f"data/video/*.{suffix}" in attributes, suffix
    assert "filter=lfs" in attributes
    # Factory footage stays out of git whatever its extension.
    assert is_ignored("data/factory/line3.mkv")


def test_secret_files_are_ignored_but_guide_is_tracked() -> None:
    # Keys live in .env; .secrets/ keeps only the guide for obtaining them.
    assert is_ignored(".secrets/secrets.env")
    assert is_ignored(".secrets/openrouter.key")
    assert not is_ignored(".secrets/README.md")


def test_ac_06_the_env_file_holding_every_key_is_ignored() -> None:
    assert is_ignored(".env")
    assert not is_ignored(".env.example")


def test_tracked_example_files_exist() -> None:
    for name in (".env.example", ".secrets/README.md"):
        assert Path(REPO_ROOT / name).is_file(), name
