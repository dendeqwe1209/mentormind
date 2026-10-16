"""Token counting for the chunker (spec 02 FR-04)."""

from __future__ import annotations

import importlib
from typing import Any, Protocol


class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...


class WhitespaceTokenCounter:
    """One token per whitespace-separated word; deterministic, used by tests."""

    def count(self, text: str) -> int:
        return len(text.split())


class BgeM3TokenCounter:
    """Counts with the tokenizer of ``KNOWHOW_EMBED_MODEL`` so chunks fit the embedder.

    The tokenizer loads on first use; ``transformers`` is imported lazily so the rest of ingest
    works without the extra.
    """

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._tokenizer: Any = None

    def count(self, text: str) -> int:
        if self._tokenizer is None:
            try:
                transformers = importlib.import_module("transformers")
            except ImportError as exc:
                raise RuntimeError("Cần cài extra `ingest` (transformers) để đếm token bằng bge-m3.") from exc
            self._tokenizer = transformers.AutoTokenizer.from_pretrained(self._model_name)
        return len(self._tokenizer.encode(text, add_special_tokens=False))
