"""Rasterize a synthetic PDF into a fake scan (slight skew + noise) for spec 02 AC-03.

Usage: uv run python scripts/make_scan_sample.py data/demo/packing/packing_sop.pdf data/samples/docs/packing_sop_scan.pdf
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from PIL import Image

SEED = 20260930
DPI = 150
SKEW_DEGREES = 0.8
NOISE_SIGMA = 6.0


def main(src: Path, dst: Path) -> None:
    rng = np.random.default_rng(SEED)
    pages: list[Image.Image] = []
    for page in pdfium.PdfDocument(str(src)):
        image = page.render(scale=DPI / 72).to_pil().convert("L")
        image = image.rotate(SKEW_DEGREES, resample=Image.Resampling.BICUBIC, fillcolor=255)
        noisy = np.asarray(image, dtype=np.float32) + rng.normal(0, NOISE_SIGMA, (image.height, image.width))
        pages.append(Image.fromarray(np.clip(noisy, 0, 255).astype(np.uint8)))
    dst.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(dst, save_all=True, append_images=pages[1:], resolution=DPI)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
