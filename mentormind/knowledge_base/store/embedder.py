"""bge-m3 dense embedders (spec 02 FR-07, FR-07d): text -> unit vector of 1024 floats.

:class:`BgeM3Embedder` runs on this machine. The model (~2.2 GB) downloads from Hugging Face on
first use; ``torch``/``transformers`` come with the ``ingest`` extra and are imported only then,
so everything else works without them. :class:`RemoteEmbedder` asks the team's inference server
for the same vectors (``KNOWHOW_EMBEDDER=remote``) and runs ``DataGuard`` before each request
(constitution art. 2: factory-confidential text never goes to a cloud URL).
"""

from __future__ import annotations

import importlib
import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from mentormind.core.guard import DataGuard
from mentormind.core.providers.errors import ProviderError
from mentormind.core.providers.inference import InferenceClient
from mentormind.core.schemas.common import DataClassification
from mentormind.knowledge_base.store.vector_store import VectorStoreError

#: Texts in -> raw (unnormalised) CLS vectors out. The only part that touches torch.
Forward = Callable[[list[str]], list[list[float]]]

DEFAULT_MODEL = "BAAI/bge-m3"
DEFAULT_DIM = 1024
# Chunks are at most 800 bge-m3 tokens (spec 02 FR-04); the model itself accepts up to 8192.
_MAX_LENGTH = 1024


class BgeM3Embedder:
    """Implements ``Embedder``. The model loads on the first non-empty ``embed`` call."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        *,
        dim: int = DEFAULT_DIM,
        batch_size: int = 16,
        forward: Forward | None = None,
    ) -> None:
        if batch_size < 1:
            raise ValueError(f"batch_size phải >= 1, nhận {batch_size}.")
        self._model_name = model_name
        self._dim = dim
        self._batch_size = batch_size
        self._forward = forward

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed ``texts`` in order, ``batch_size`` at a time.

        Raises:
            VectorStoreError: ``torch``/``transformers`` are missing or the model's dimension is not ``dim``.
        """
        items = list(texts)
        if not items:
            return []
        if self._forward is None:
            self._forward = _load_forward(self._model_name)
        out: list[list[float]] = []
        for start in range(0, len(items), self._batch_size):
            for vector in self._forward(items[start : start + self._batch_size]):
                if len(vector) != self._dim:
                    raise VectorStoreError(
                        f"Model {self._model_name} sinh vector {len(vector)} chiều, store cần {self._dim}."
                    )
                out.append(_normalise(vector))
        return out


class RemoteEmbedder:
    """Implements ``Embedder`` with ``POST {KNOWHOW_INFERENCE_URL}/embeddings`` (spec 02 FR-07d).

    Also a ``ClassifiedEmbedder``: the store passes the label of the chunks it embeds. Text that
    comes without one (a search query, an agent's question) is treated as ``factory_confidential``,
    the strictest label, so a cloud URL never receives it.
    """

    def __init__(
        self,
        client: InferenceClient,
        *,
        model_name: str = DEFAULT_MODEL,
        dim: int = DEFAULT_DIM,
        batch_size: int = 32,
    ) -> None:
        if batch_size < 1:
            raise ValueError(f"batch_size phải >= 1, nhận {batch_size}.")
        self._client = client
        self._model_name = model_name
        self._dim = dim
        self._batch_size = batch_size

    @property
    def name(self) -> str:
        return self._client.name

    @property
    def is_cloud(self) -> bool:
        return self._client.is_cloud

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Unlabelled text (a question) counts as ``factory_confidential``."""
        return self.embed_classified(texts, DataClassification.FACTORY_CONFIDENTIAL)

    def embed_classified(self, texts: Sequence[str], classification: DataClassification | str) -> list[list[float]]:
        """Embed ``texts`` in order, ``batch_size`` per request, after ``DataGuard`` allowed the label.

        Raises:
            ConfidentialDataError: ``factory_confidential`` text and a cloud URL — nothing was sent.
            VectorStoreError: the server failed or answered vectors of the wrong number or size.
        """
        DataGuard.check(classification, self)
        items = list(texts)
        out: list[list[float]] = []
        for start in range(0, len(items), self._batch_size):
            batch = items[start : start + self._batch_size]
            try:
                body = self._client.post_json("/embeddings", {"model": self._model_name, "input": batch})
            except ProviderError as exc:
                raise VectorStoreError(f"Máy chủ suy luận không embed được: {exc}") from exc
            out.extend(_normalise(vector) for vector in self._vectors(body, len(batch)))
        return out

    def _vectors(self, body: Mapping[str, Any], expected: int) -> list[list[float]]:
        try:
            rows = sorted(body["data"], key=lambda row: int(row["index"]))
            vectors = [[float(x) for x in row["embedding"]] for row in rows]
        except (KeyError, TypeError, ValueError) as exc:
            raise VectorStoreError(f"Máy chủ suy luận trả embedding sai dạng: {str(body)[:300]}") from exc
        if [int(row["index"]) for row in rows] != list(range(expected)):
            raise VectorStoreError(f"Máy chủ suy luận trả {len(rows)} vector cho {expected} đoạn văn.")
        for vector in vectors:
            if len(vector) != self._dim:
                raise VectorStoreError(
                    f"Model {self._model_name} trên máy chủ sinh vector {len(vector)} chiều, store cần {self._dim}."
                )
        return vectors


def _normalise(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector] if norm else vector


def _load_forward(model_name: str) -> Forward:
    try:
        torch = importlib.import_module("torch")
        transformers = importlib.import_module("transformers")
    except ImportError as exc:
        raise VectorStoreError("Thiếu torch/transformers: cài extra `ingest` (uv sync --extra ingest).") from exc
    tokenizer = transformers.AutoTokenizer.from_pretrained(model_name)
    model = transformers.AutoModel.from_pretrained(model_name).eval()

    def forward(texts: list[str]) -> list[list[float]]:
        batch = tokenizer(texts, padding=True, truncation=True, max_length=_MAX_LENGTH, return_tensors="pt")
        with torch.no_grad():
            hidden = model(**batch).last_hidden_state
        return [[float(x) for x in row] for row in hidden[:, 0].tolist()]  # bge-m3 dense = the [CLS] vector

    return forward
