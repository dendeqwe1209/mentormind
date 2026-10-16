"""Fixtures shared by every test package."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image


@pytest.fixture
def frames(tmp_path: Path) -> list[Path]:
    paths = []
    for i, color in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255)]):
        path = tmp_path / f"frame_{i}.jpg"
        Image.new("RGB", (64, 36), color).save(path, format="JPEG")
        paths.append(path)
    return paths
