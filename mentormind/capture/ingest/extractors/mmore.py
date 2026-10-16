"""mmore fast extractor: degraded text-only fallback for PDFs (spec 02 FR-02, proposal 5).

Fast mode reads the text layer with PyMuPDF: no OCR and table structure is lost, so the result
is flagged ``metadata.degraded``. It runs ``mmore process`` on a temporary copy of the file.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from mentormind.capture.ingest.extractors.base import ExtractorError
from mentormind.capture.ingest.raw import RawBlock, RawDocument
from mentormind.core.schemas import ChunkKind

_STDERR_CHARS = 500


class MmoreFastExtractor:
    name = "mmore"

    def __init__(self, binary: str = "mmore", timeout_s: float = 300.0) -> None:
        self._binary = binary
        self._timeout_s = timeout_s

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    def extract(self, path: Path) -> RawDocument:
        with tempfile.TemporaryDirectory(prefix="knowhow-mmore-") as tmp:
            root = Path(tmp)
            (root / "in").mkdir()
            shutil.copy(path, root / "in" / path.name)
            config = root / "config.yaml"
            config.write_text(
                f"data_path: {root / 'in'}\n"
                "google_drive_ids: []\n"
                "dispatcher_config:\n"
                f"  output_path: {root / 'out'}\n"
                "  use_fast_processors: true\n"
                "  extract_images: false\n"
            )
            try:
                proc = subprocess.run(
                    [self._binary, "process", "--config-file", str(config)],
                    capture_output=True,
                    text=True,
                    timeout=self._timeout_s,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ExtractorError(f"Không chạy được mmore ({self._binary}): {exc}") from exc
            if proc.returncode != 0:
                raise ExtractorError(f"mmore thoát mã {proc.returncode}: {proc.stderr[-_STDERR_CHARS:]}")
            merged = root / "out" / "merged" / "merged_results.jsonl"
            lines = merged.read_text().splitlines() if merged.exists() else []
            if not lines:
                raise ExtractorError(f"mmore không trả kết quả cho {path.name}.")
            return parse_mmore_record(json.loads(lines[0]), path)


def parse_mmore_record(record: dict[str, Any], path: Path) -> RawDocument:
    """One mmore sample -> one text block per page; fast mode numbers pages from 0."""
    text: str = record.get("text", "")
    starts = [tuple(s) for s in record.get("metadata", {}).get("paragraph_starts") or []]
    bounds: dict[int, list[int]] = {}
    for (offset, page, _para), (end, _p, _q) in zip(starts, starts[1:], strict=False):
        if page >= 0:
            span = bounds.setdefault(page, [offset, end])
            span[1] = end
    blocks = [
        RawBlock(kind=ChunkKind.TEXT, text=text[lo:hi].strip(), page=page + 1)
        for page, (lo, hi) in sorted(bounds.items())
        if text[lo:hi].strip()
    ]
    if not bounds and text.strip():
        blocks = [RawBlock(kind=ChunkKind.TEXT, text=text.strip(), page=None)]
    return RawDocument(
        path=str(path),
        num_pages=len(bounds),
        blocks=blocks,
        extractor="mmore",
        metadata={"degraded": True},
    )
