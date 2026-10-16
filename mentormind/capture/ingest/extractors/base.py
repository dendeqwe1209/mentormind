"""The extractor interface (constitution art. 5): tools sit behind it so tests use fakes."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from mentormind.capture.ingest.raw import RawDocument


class ExtractorError(Exception):
    """An extractor could not read the file; the message says why and what to do."""


class Extractor(Protocol):
    name: str

    def supports(self, path: Path) -> bool: ...

    def extract(self, path: Path) -> RawDocument:
        """Raises:
        ExtractorError: the tool is missing, crashed, or produced unusable output.
        """
        ...
