"""``Judge`` — what every judge of the four Ragas metrics shares, and the sample it scores.

``score`` is a template method: the subclass computes the metrics (``_score``), the base counts
the values it could not compute (``failures``) — never a made-up number. A subclass registers
itself under its ``kind`` (the ``KNOWHOW_EVAL_JUDGE`` value) just by being defined.
"""

from __future__ import annotations

import logging
import math
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, Protocol

from mentormind.core.providers.llm import LLMProvider
from mentormind.core.schemas import DataClassification

log = logging.getLogger(__name__)

#: Score dict of one sample: column of ``ragas_results.csv`` -> value (None = not computable).
Scores = dict[str, float | None]


@dataclass(frozen=True)
class JudgeSample:
    question: str
    answer: str
    #: Snippets of the citations the answer carries, in rank order.
    contexts: Sequence[str]
    ground_truth: str


class TextEmbedder(Protocol):
    """``knowledge_base.store.embedding.BgeM3Embedder`` (or a fake)."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class Judge(ABC):
    #: ``KNOWHOW_EVAL_JUDGE`` value, recorded in ``summary.json``.
    kind: ClassVar[str]
    #: Every judge class by ``kind`` (filled as subclasses are defined).
    registry: ClassVar[dict[str, type[Judge]]] = {}

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        cls.registry[cls.kind] = cls

    def __init__(self, llm: LLMProvider, embedder: TextEmbedder) -> None:
        self.llm = llm
        self.embedder = embedder
        #: Metric values that could not be computed, over every ``score`` call.
        self.failures = 0

    def score(self, samples: Sequence[JudgeSample], label: DataClassification) -> list[Scores]:
        """One dict of the four metrics per sample, in order. Raises ``ConfidentialDataError``."""
        rows = self._score(samples, label) if samples else []
        missing = sum(value is None for row in rows for value in row.values())
        if missing:
            log.warning("%s judge could not compute %d metric values", self.kind, missing)
        self.failures += missing
        return rows

    @abstractmethod
    def _score(self, samples: Sequence[JudgeSample], label: DataClassification) -> list[Scores]:
        """The four metrics of every sample (``None`` where not computable); ``samples`` is not empty."""


def round_score(value: object) -> float | None:
    """A score rounded like the summary; NaN and non-numbers -> None (never a made-up number)."""
    if isinstance(value, int | float) and not math.isnan(value):
        return round(float(value), 3)
    return None
