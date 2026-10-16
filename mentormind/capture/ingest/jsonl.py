"""Chunk files: one ``DocumentChunk`` per line, written atomically (spec 02 FR-06)."""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from pathlib import Path

from pydantic import ValidationError

from mentormind.core.schemas import DocumentChunk


class ChunkFileError(ValueError):
    """A line of a chunk file is not a valid ``DocumentChunk``."""

    def __init__(self, file: Path, line_no: int, message: str) -> None:
        super().__init__(f"{file}: dòng {line_no}: {message}")
        self.file = file
        self.line_no = line_no


def write_chunks_atomic(path: Path, chunks: Iterable[DocumentChunk]) -> int:
    """Write via a temp file then ``os.replace``: a failure leaves no partial file and keeps the old one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    count = 0
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            for chunk in chunks:
                handle.write(chunk.model_dump_json() + "\n")
                count += 1
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return count


def read_chunks(path: Path) -> Iterator[tuple[int, DocumentChunk]]:
    """Yield ``(line_no, chunk)``; a bad line raises :class:`ChunkFileError` naming file and line."""
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                yield line_no, DocumentChunk.model_validate_json(line)
            except ValidationError as exc:
                raise ChunkFileError(path, line_no, str(exc).splitlines()[0]) from exc
