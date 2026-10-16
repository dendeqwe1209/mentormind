"""Data labels of what the agents retrieve; a missing label is factory data (fail closed)."""

from __future__ import annotations

from typing import Any

from mentormind.core.providers.llm import strictest
from mentormind.core.schemas import DataClassification
from mentormind.knowledge_base.retrieval.hybrid import RetrievedContext


def passage_label(context: RetrievedContext, index: int) -> DataClassification:
    """Label of ``context.passages[index]``."""
    if index < len(context.classifications):
        return context.classifications[index]
    return DataClassification.FACTORY_CONFIDENTIAL


def row_label(row: dict[str, Any]) -> DataClassification:
    """Strictest label of a graph row (one label, or the labels of every node it is built from)."""
    value = row.get("data_classification")
    labels = value if isinstance(value, list) else [value]
    return strictest(
        DataClassification(label) if label else DataClassification.FACTORY_CONFIDENTIAL for label in labels or [None]
    )
