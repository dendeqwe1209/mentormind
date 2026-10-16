"""Local BGE-M3 dense embeddings for the PostgreSQL vector index."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from mentormind.knowledge_base.store.vector_store import VectorStoreError


class BgeM3Embedder:
    def __init__(self, model_name: str = "BAAI/bge-m3") -> None:
        self.model_name = model_name
        self._model: Any = None

    @property
    def dim(self) -> int:
        return 1024

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise VectorStoreError("Install semantic KG support: uv sync --extra kg-semantic") from exc
            try:
                self._model = SentenceTransformer(self.model_name, local_files_only=True)
            except (OSError, ValueError) as exc:
                raise VectorStoreError(f"Embedding model {self.model_name!r} is not cached locally") from exc
        vectors = self._model.encode(list(texts), normalize_embeddings=True)
        result: list[list[float]] = vectors.tolist()
        if any(len(vector) != self.dim for vector in result):
            raise VectorStoreError(f"Embedding model {self.model_name!r} must return 1024 dimensions")
        return result
