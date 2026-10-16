"""Near-duplicate frame removal: 64-bit dHash, Hamming distance to the last KEPT frame."""

from __future__ import annotations

from PIL import Image

DUPLICATE_MAX_HAMMING = 4


def dhash(image: Image.Image) -> int:
    """64-bit difference hash: is each pixel brighter than its right neighbour (9x8 grey)."""
    small = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = small.tobytes()  # one byte per pixel in "L" mode
    bits = 0
    for row in range(8):
        for col in range(8):
            left, right = pixels[row * 9 + col], pixels[row * 9 + col + 1]
            bits = (bits << 1) | int(left > right)
    return bits


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def drop_near_duplicates(
    frames: list[tuple[float, Image.Image]],
) -> list[tuple[float, Image.Image]]:
    kept: list[tuple[float, Image.Image]] = []
    last_hash: int | None = None
    for t, image in frames:
        h = dhash(image)
        if last_hash is not None and hamming(h, last_hash) <= DUPLICATE_MAX_HAMMING:
            continue
        kept.append((t, image))
        last_hash = h
    return kept
