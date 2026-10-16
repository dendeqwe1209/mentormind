"""Near-duplicate detection by dHash distance."""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from mentormind.processing.vlm.frames import (
    DUPLICATE_MAX_HAMMING,
    dhash,
    hamming,
)


def noise_frames(count: int, size: tuple[int, int] = (120, 160), seed: int = 0) -> list[np.ndarray]:
    """Every frame different: random blocks, upscaled so compression keeps them distinct."""
    rng = np.random.default_rng(seed)
    height, width = size
    frames = []
    for _ in range(count):
        blocks = rng.integers(0, 256, (height // 8, width // 8, 3), dtype=np.uint8)
        frames.append(cv2.resize(blocks, (width, height), interpolation=cv2.INTER_NEAREST))
    return frames


def still_frames(count: int, size: tuple[int, int] = (120, 160)) -> list[np.ndarray]:
    """Identical frames with structure (a flat image would make dHash bits noise-driven)."""
    height, width = size
    base = np.zeros((height, width, 3), dtype=np.uint8)
    base[:, :, 1] = np.linspace(0, 255, width, dtype=np.uint8)[None, :]
    cv2.rectangle(base, (30, 30), (90, 90), (255, 255, 255), -1)
    return [base.copy() for _ in range(count)]


def test_dhash_distance_separates_duplicates_from_changes() -> None:
    still = Image.fromarray(still_frames(1)[0])
    changed = Image.fromarray(noise_frames(1)[0])
    assert hamming(dhash(still), dhash(still.copy())) == 0
    assert hamming(dhash(still), dhash(changed)) > DUPLICATE_MAX_HAMMING
