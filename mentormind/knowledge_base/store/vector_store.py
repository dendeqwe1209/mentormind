"""``VectorStore`` — the vector table behind an interface (spec 01 FR-05c, constitution art. 5).

Backends, chosen by ``KNOWHOW_VECTOR_BACKEND``:

* ``memory`` — in-process: dense cosine over the store's embedder plus BM25 over accent-folded
  tokens, fused by Reciprocal Rank Fusion (k=60, the fusion of spec 05). For unit tests / CI
  without Docker (AC-08).
* ``pgvector`` — ``public.knowhow_chunks`` of ``infra/postgres/init.sql``
  (:mod:`mentormind.knowledge_base.store.pgvector_store`); needs the ``ingest`` extra and a
  running Postgres (``make up``).

Filters are exact matches on ``source_type``, ``kind``, ``ref_id`` (alias ``doc_id``) and
``data_classification``; ``process_ids`` / ``part_numbers`` (singular spellings accepted) match when
the chunk lists the value. Every filter value may be a single value or a list ("any of"); an empty
list matches nothing; several keys combine with AND.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from mentormind.core.config import Settings, get_settings
from mentormind.core.providers.llm.context import strictest
from mentormind.core.schemas.common import DataClassification
from mentormind.core.schemas.vector import VectorChunk, VectorHit

RRF_K = 60
_BM25_K1 = 1.5
_BM25_B = 0.75
_TOKEN = re.compile(r"\w+")
_EXACT_FILTERS = {
    "source_type": "source_type",
    "kind": "kind",
    "ref_id": "ref_id",
    "doc_id": "ref_id",  # for document chunks ref_id is the doc_id (spec 02 FR-07)
    "data_classification": "data_classification",
}
_ARRAY_FILTERS = {
    "process_id": "process_ids",
    "process_ids": "process_ids",
    "part_number": "part_numbers",
    "part_numbers": "part_numbers",
}


@dataclass(frozen=True)
class FilterClause:
    """One validated filter: ``column`` is a ``VectorChunk`` field, never user text."""

    column: str
    values: list[str]
    is_array: bool


def parse_filters(filters: Mapping[str, Any]) -> list[FilterClause]:
    """Validate ``filters`` once for every backend; values may be one value or a list ("any of").

    Raises:
        ValueError: a key is not a supported filter (also what keeps raw text out of SQL).
    """
    clauses = []
    for key, wanted in filters.items():
        if key not in _EXACT_FILTERS and key not in _ARRAY_FILTERS:
            raise ValueError(f"Filter không hỗ trợ: {key!r}")
        values = [str(wanted)] if isinstance(wanted, str) else [str(v) for v in wanted]
        if key in _EXACT_FILTERS:
            clauses.append(FilterClause(_EXACT_FILTERS[key], values, False))
        else:
            clauses.append(FilterClause(_ARRAY_FILTERS[key], values, True))
    return clauses


def require_filters(filters: Mapping[str, Any]) -> list[FilterClause]:
    """:func:`parse_filters` for destructive calls: an empty filter is refused, never "everything"."""
    if not filters:
        raise ValueError("delete_where cần ít nhất một filter (không xóa cả bảng).")
    return parse_filters(filters)


class VectorStoreError(RuntimeError):
    """The configured vector backend cannot be used."""


class Embedder(Protocol):
    """Text -> dense vector. The real one (bge-m3, 1024 dims) arrives with spec 02."""

    @property
    def dim(self) -> int: ...

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


@runtime_checkable
class ClassifiedEmbedder(Protocol):
    """An embedder that sends the text off this process (``RemoteEmbedder``, spec 02 FR-07d).

    It is told the label of what it embeds so ``DataGuard`` runs before anything is sent; its
    plain ``embed`` treats unlabelled text as ``factory_confidential``.
    """

    def embed_classified(self, texts: Sequence[str], classification: DataClassification | str) -> list[list[float]]: ...


class VectorStore(Protocol):
    """The surface every backend offers (spec 01 FR-05c)."""

    def upsert(self, chunks: Iterable[VectorChunk]) -> int:
        """Insert or replace by ``chunk_id``; returns how many chunks were written."""
        ...

    def search(self, query: str, k: int = 8, filters: Mapping[str, Any] | None = None) -> list[VectorHit]:
        """Top ``k`` chunks for ``query`` that pass ``filters``, best first."""
        ...

    def delete(self, ids: Iterable[str]) -> int:
        """Remove chunks by ``chunk_id``; returns how many existed."""
        ...

    def delete_where(self, filters: Mapping[str, Any]) -> int:
        """Remove every chunk passing ``filters`` (same syntax as ``search``); returns how many.

        Raises:
            ValueError: ``filters`` is empty (that would wipe the table) or has an unsupported key.
        """
        ...


def tokens(text: str) -> list[str]:
    """Lower-case, accent-folded word tokens ("Tránh trầy" -> ["tranh", "tray"])."""
    decomposed = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    folded = "".join(c for c in decomposed if not unicodedata.combining(c)).lower()
    return _TOKEN.findall(folded)


class HashingEmbedder:
    """Deterministic bag-of-words embedder (feature hashing): no model, no network.

    Good enough for tests and the offline demo; semantic search needs the real embedder.
    """

    def __init__(self, dim: int = 256) -> None:
        if dim <= 0:
            raise ValueError("dim must be positive")
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._one(text) for text in texts]

    def _one(self, text: str) -> list[float]:
        vector = [0.0] * self._dim
        for token in tokens(text):
            digest = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "big")
            vector[digest % self._dim] += 1.0 if digest >> 63 else -1.0
        norm = math.sqrt(sum(v * v for v in vector))
        return [v / norm for v in vector] if norm else vector


def embed_missing(chunks: Iterable[VectorChunk], embedder: Embedder) -> list[VectorChunk]:
    """Fill ``embedding`` where absent; a supplied one must have the embedder's dimension.

    An embedder that sends text away (:class:`ClassifiedEmbedder`) is told the strictest label of
    the chunks it embeds, so a cloud one refuses ``factory_confidential`` chunks before any request.

    Raises:
        VectorStoreError: a supplied embedding has the wrong size.
        ConfidentialDataError: ``factory_confidential`` chunks and an embedder at a cloud URL.
    """
    batch = list(chunks)
    missing = [c for c in batch if c.embedding is None]
    vectors = iter(_embed_chunks(embedder, missing))
    out = []
    for chunk in batch:
        if chunk.embedding is None:
            chunk = chunk.model_copy(update={"embedding": next(vectors)})
        elif len(chunk.embedding) != embedder.dim:
            raise VectorStoreError(
                f"Chunk {chunk.chunk_id}: embedding có {len(chunk.embedding)} chiều, store cần {embedder.dim}."
            )
        out.append(chunk)
    return out


def _embed_chunks(embedder: Embedder, chunks: Sequence[VectorChunk]) -> list[list[float]]:
    if not chunks:
        return []
    texts = [c.text for c in chunks]
    if isinstance(embedder, ClassifiedEmbedder):
        return embedder.embed_classified(texts, strictest(c.data_classification for c in chunks))
    return embedder.embed(texts)


class MemoryVectorStore:
    """In-process :class:`VectorStore`: cosine + BM25, fused by RRF."""

    def __init__(self, embedder: Embedder | None = None) -> None:
        self._embedder = embedder or HashingEmbedder()
        self._chunks: dict[str, VectorChunk] = {}

    def upsert(self, chunks: Iterable[VectorChunk]) -> int:
        batch = embed_missing(chunks, self._embedder)
        for chunk in batch:
            self._chunks[chunk.chunk_id] = chunk
        return len(batch)

    def search(self, query: str, k: int = 8, filters: Mapping[str, Any] | None = None) -> list[VectorHit]:
        clauses = parse_filters(filters or {})
        candidates = [c for c in self._chunks.values() if _passes(c, clauses)]
        if not candidates or k <= 0:
            return []
        query_vector = self._embedder.embed([query])[0]
        dense = sorted(candidates, key=lambda c: _cosine(query_vector, c.embedding or []), reverse=True)
        lexical_scores = _bm25(tokens(query), candidates)
        lexical = sorted(
            (c for c in candidates if lexical_scores[c.chunk_id] > 0),
            key=lambda c: lexical_scores[c.chunk_id],
            reverse=True,
        )
        fused: dict[str, float] = {}
        for ranking in (dense, lexical):
            for rank, chunk in enumerate(ranking, start=1):
                fused[chunk.chunk_id] = fused.get(chunk.chunk_id, 0.0) + 1.0 / (RRF_K + rank)
        best = sorted(fused.items(), key=lambda item: item[1], reverse=True)[:k]
        return [VectorHit(chunk=self._chunks[cid], score=round(score, 6)) for cid, score in best]

    def delete(self, ids: Iterable[str]) -> int:
        return sum(self._chunks.pop(i, None) is not None for i in ids)

    def delete_where(self, filters: Mapping[str, Any]) -> int:
        clauses = require_filters(filters)
        doomed = [cid for cid, c in self._chunks.items() if _passes(c, clauses)]
        return self.delete(doomed)


def get_vector_store(settings: Settings | None = None, *, embedder: Embedder | None = None) -> VectorStore:
    """The backend selected by ``KNOWHOW_VECTOR_BACKEND`` (only config changes, art. 5).

    PostgreSQL mode uses the table defined in ``infra/postgres/init.sql``.

    Raises:
        VectorStoreError: ``pgvector`` is selected but its driver, embedder or table is not usable.
    """
    settings = settings or get_settings()
    if settings.vector_backend == "memory":
        return MemoryVectorStore(embedder)
    try:
        from mentormind.knowledge_base.store.pgvector_store import PgVectorStore
    except ImportError as exc:
        raise VectorStoreError("Thiếu psycopg: cài extra `ingest` (uv sync --extra ingest).") from exc
    return PgVectorStore(settings.pg_dsn, settings.vector_table, embedder or get_embedder(settings))


def get_embedder(settings: Settings | None = None) -> Embedder:
    """The embedder selected by ``KNOWHOW_EMBEDDER``: bge-m3 here, bge-m3 on the inference server, hashing.

    Raises:
        VectorStoreError: ``remote`` without ``KNOWHOW_INFERENCE_URL``.
    """
    settings = settings or get_settings()
    if settings.embedder == "hashing":
        return HashingEmbedder(settings.embed_dim)
    if settings.embedder == "remote":
        from mentormind.core.providers.errors import ProviderConfigError
        from mentormind.core.providers.inference import InferenceClient
        from mentormind.knowledge_base.store.embedder import RemoteEmbedder

        try:
            client = InferenceClient.from_settings(settings)
        except ProviderConfigError as exc:
            raise VectorStoreError(str(exc)) from exc
        return RemoteEmbedder(client, model_name=settings.embed_model, dim=settings.embed_dim)
    from mentormind.knowledge_base.store.embedder import BgeM3Embedder

    return BgeM3Embedder(settings.embed_model, dim=settings.embed_dim)


def _passes(chunk: VectorChunk, clauses: Sequence[FilterClause]) -> bool:
    for clause in clauses:
        held = getattr(chunk, clause.column)
        if clause.is_array:
            if not any(value in held for value in clause.values):
                return False
        elif held not in clause.values:
            return False
    return True


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def _bm25(query: list[str], chunks: Sequence[VectorChunk]) -> dict[str, float]:
    docs = {c.chunk_id: Counter(tokens(c.text)) for c in chunks}
    lengths = {cid: sum(tf.values()) for cid, tf in docs.items()}
    average = sum(lengths.values()) / len(docs) or 1.0
    scores = dict.fromkeys(docs, 0.0)
    for term in set(query):
        having = sum(1 for tf in docs.values() if term in tf)
        if not having:
            continue
        idf = math.log(1 + (len(docs) - having + 0.5) / (having + 0.5))
        for cid, tf in docs.items():
            f = tf.get(term, 0)
            if f:
                norm = 1 - _BM25_B + _BM25_B * lengths[cid] / average
                scores[cid] += idf * f * (_BM25_K1 + 1) / (f + _BM25_K1 * norm)
    return scores
