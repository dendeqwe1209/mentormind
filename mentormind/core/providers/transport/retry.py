"""Retry policy for provider calls: bounded retries with exponential backoff (spec 04 FR-07)."""

from __future__ import annotations

import random
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field


class RetryPolicy(BaseModel):
    """Retry transient failures (429, 5xx, network) at most ``max_retries`` times."""

    model_config = ConfigDict(frozen=True)

    max_retries: int = Field(default=3, ge=0)
    base_delay_s: float = Field(default=1.0, ge=0)
    max_delay_s: float = Field(default=20.0, ge=0)
    retriable_statuses: frozenset[int] = frozenset({408, 409, 429, 500, 502, 503, 504})
    jitter: Callable[[], float] = Field(default=lambda: random.uniform(0.0, 0.5), exclude=True)

    def delay_for(self, retry_index: int, retry_after: float | None = None) -> float:
        """Seconds to wait before retry number ``retry_index`` (0-based)."""
        if retry_after is not None:
            return min(retry_after, self.max_delay_s)
        return min(self.base_delay_s * 2**retry_index + self.jitter(), self.max_delay_s)
