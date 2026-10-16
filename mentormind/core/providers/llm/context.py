"""Context passages for an LLM prompt, filtered by where the prompt goes (spec 06 §2, AC-04).

A cloud provider never receives a ``factory_confidential`` passage: it is dropped from the
context (and the number dropped is logged), so the rest of the answer can still be grounded.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence

from pydantic import BaseModel, ConfigDict

from mentormind.core.guard import SupportsCloudFlag
from mentormind.core.schemas.common import DataClassification

log = logging.getLogger(__name__)

_RANK = {
    DataClassification.PUBLIC: 0,
    DataClassification.SYNTHETIC: 1,
    DataClassification.FACTORY_CONFIDENTIAL: 2,
}


class ContextPassage(BaseModel):
    """One retrieved passage and the label of the data it came from."""

    model_config = ConfigDict(frozen=True)

    ref_id: str
    text: str
    classification: DataClassification


def filter_passages(passages: Sequence[ContextPassage], destination: SupportsCloudFlag) -> list[ContextPassage]:
    """Passages ``destination`` may receive; confidential ones are dropped for the cloud."""
    if not destination.is_cloud:
        return list(passages)
    kept = [p for p in passages if p.classification is not DataClassification.FACTORY_CONFIDENTIAL]
    dropped = len(passages) - len(kept)
    if dropped:
        log.info(
            "Dropped %d factory_confidential passage(s) before calling cloud provider %s",
            dropped,
            destination.name,
        )
    return kept


def strictest(labels: Iterable[DataClassification]) -> DataClassification:
    """The most restrictive label (what a prompt built from these passages is)."""
    return max(labels, key=lambda label: _RANK[label], default=DataClassification.PUBLIC)
