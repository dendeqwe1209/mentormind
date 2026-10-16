"""Traces of agent calls (spec 06 FR-04): one JSON line per call under ``data/work/traces/``.

Each line: request, the context ids the agent used, a hash of every prompt sent, the response, the
latency and the agent's own metrics — enough to debug an answer and to feed the evaluation of spec 09.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


def prompt_hash(prompt: str) -> str:
    return "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


class TraceRecord(BaseModel):
    trace_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    #: ``ask`` or ``rca``.
    kind: str
    request: dict[str, Any]
    context_ids: list[str]
    prompt_hashes: list[str]
    response: dict[str, Any]
    latency_s: float
    llm: str
    #: The agent's own numbers (Work Assistant: max_rrf, max_cosine, blocked_by).
    metrics: dict[str, Any] = Field(default_factory=dict)


class TraceLog:
    """Appends to ``<directory>/<kind>-YYYYMMDD.jsonl``; ``None`` disables tracing."""

    def __init__(self, directory: Path | None) -> None:
        self._directory = directory

    def write(
        self,
        *,
        kind: str,
        request: BaseModel,
        context_ids: Sequence[str],
        prompts: Sequence[str],
        response: BaseModel,
        latency_s: float,
        llm: str,
        metrics: dict[str, Any] | None = None,
    ) -> TraceRecord:
        record = TraceRecord(
            kind=kind,
            request=request.model_dump(mode="json"),
            context_ids=list(context_ids),
            prompt_hashes=[prompt_hash(p) for p in prompts],
            response=response.model_dump(mode="json"),
            latency_s=round(latency_s, 3),
            llm=llm,
            metrics=dict(metrics or {}),
        )
        if self._directory is not None:
            self._directory.mkdir(parents=True, exist_ok=True)
            path = self._directory / f"{kind}-{record.ts:%Y%m%d}.jsonl"
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=False) + "\n")
        return record
