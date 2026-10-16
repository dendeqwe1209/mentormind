"""Pick an extractor and fall back down the chain (spec 02 FR-02, AC-11, proposal 5)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from mentormind.capture.ingest.extractors.base import Extractor, ExtractorError
from mentormind.capture.ingest.raw import RawDocument


def extract_with_fallback(path: Path, extractors: Sequence[Extractor]) -> tuple[RawDocument, list[str]]:
    """Try each extractor that supports ``path`` in order; return the first usable result.

    A result with 0 blocks counts as a failure. Returns the document and the reasons earlier
    extractors were skipped (for the FR-08 log). Only ``ExtractorError`` triggers a fallback, so a
    programming error is never hidden.

    Raises:
        ExtractorError: no extractor supports the file, or all of them failed (all reasons listed).
    """
    candidates = [e for e in extractors if e.supports(path)]
    if not candidates:
        raise ExtractorError(f"{path.name}: không extractor nào hỗ trợ định dạng {path.suffix!r}.")
    reasons: list[str] = []
    for extractor in candidates:
        try:
            document = extractor.extract(path)
        except ExtractorError as exc:
            reasons.append(f"{extractor.name}: {exc}")
            continue
        if document.blocks:
            return document, reasons
        reasons.append(f"{extractor.name}: 0 khối")
    raise ExtractorError(f"{path.name}: mọi extractor đều thất bại — " + "; ".join(reasons))
