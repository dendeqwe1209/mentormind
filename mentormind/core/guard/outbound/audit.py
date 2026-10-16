"""Audit log of outbound (cloud) calls: one JSON line per call, counts only — never values."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class AuditRecord(BaseModel):
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    kind: str  # provider kind: "VLM", "LLM"
    provider: str
    model: str
    classification: str
    frames: int = 0
    masked_counts: dict[str, int] = Field(default_factory=dict)
    faces_blurred: int = 0
    level: Literal["Info", "SecurityAlert"] = "Info"
    detected_kind: str | None = None
    duration_ms: int | None = None


class AuditLog:
    """Appends records to ``<directory>/outbound-YYYYMMDD.jsonl``; ``None`` disables logging."""

    def __init__(self, directory: Path | None) -> None:
        self._directory = directory

    def write(self, record: AuditRecord) -> None:
        if self._directory is None:
            return
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._directory / f"outbound-{record.ts:%Y%m%d}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(record.model_dump_json() + "\n")
