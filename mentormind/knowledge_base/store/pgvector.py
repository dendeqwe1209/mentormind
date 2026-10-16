"""PostgreSQL vector store using HNSW cosine and accent folded full text RRF."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from mentormind.core.schemas.vector import VectorChunk, VectorHit
from mentormind.knowledge_base.store.embedding import BgeM3Embedder
from mentormind.knowledge_base.store.vector_store import Embedder, VectorStoreError


class PgVectorStore:
    def __init__(
        self,
        dsn: str,
        table: str = "knowhow_chunks",
        embedder: Embedder | None = None,
        embed_model: str = "BAAI/bge-m3",
    ):
        if not re.fullmatch(r"[a-z][a-z0-9_]*", table):
            raise ValueError("Invalid vector table name")
        try:
            import psycopg
        except ImportError as exc:
            raise VectorStoreError("Install the kg extra: uv sync --extra kg") from exc
        self._psycopg = psycopg
        self.dsn = dsn
        self.table = f"public.{table}"
        if embedder is not None and getattr(embedder, "model_name", None) != embed_model:
            raise VectorStoreError("Embedder model identity must match the configured embedding model")
        self.embedder = embedder or BgeM3Embedder(embed_model)
        self.embed_model = embed_model
        if self.embedder.dim != 1024:
            raise VectorStoreError("PostgreSQL table requires 1024 dimensional embeddings")

    @staticmethod
    def _literal(vector: list[float]) -> str:
        return "[" + ",".join(str(float(value)) for value in vector) + "]"

    def upsert(self, chunks: Iterable[VectorChunk]) -> int:
        batch = list(chunks)
        if not batch:
            return 0
        missing = [chunk for chunk in batch if chunk.embedding is None]
        computed = iter(self.embedder.embed([chunk.text for chunk in missing]))
        with self._psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                for chunk in batch:
                    vector = chunk.embedding if chunk.embedding is not None else next(computed)
                    if len(vector) != 1024:
                        raise VectorStoreError("PostgreSQL table requires 1024 dimensional embeddings")
                    metadata = dict(chunk.metadata)
                    if chunk.embedding is not None and metadata.get("embedding_model") != self.embed_model:
                        raise VectorStoreError(
                            f"Precomputed embedding for {chunk.chunk_id} must declare "
                            f"embedding_model={self.embed_model!r}"
                        )
                    metadata["embedding_model"] = self.embed_model
                    from psycopg.types.json import Jsonb

                    cur.execute(
                        f"INSERT INTO {self.table} "
                        "(chunk_id,source_type,ref_id,kind,text,process_ids,part_numbers,"
                        "data_classification,metadata,embedding) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector) "
                        "ON CONFLICT (chunk_id) DO UPDATE SET "
                        "source_type=excluded.source_type,ref_id=excluded.ref_id,kind=excluded.kind,"
                        "text=excluded.text,process_ids=excluded.process_ids,"
                        "part_numbers=excluded.part_numbers,"
                        "data_classification=excluded.data_classification,metadata=excluded.metadata,"
                        "embedding=excluded.embedding",
                        (
                            chunk.chunk_id,
                            chunk.source_type,
                            chunk.ref_id,
                            chunk.kind,
                            chunk.text,
                            chunk.process_ids,
                            chunk.part_numbers,
                            str(chunk.data_classification),
                            Jsonb(metadata),
                            self._literal(vector),
                        ),
                    )
        return len(batch)

    def search(self, query: str, k: int = 8, filters: Mapping[str, Any] | None = None) -> list[VectorHit]:
        if k <= 0:
            return []
        filters = filters or {}
        where = ["metadata->>'embedding_model' = %s"]
        values = [self.embed_model]
        allowed = {"source_type", "kind", "ref_id", "data_classification"}
        for key, value in filters.items():
            if key in allowed:
                where.append(f"{key} = %s")
                values.append(value)
            elif key in {"process_id", "part_number"}:
                column = "process_ids" if key == "process_id" else "part_numbers"
                where.append(f"%s = ANY({column})")
                values.append(value)
            else:
                raise ValueError(f"Filter không hỗ trợ: {key!r}")
        predicate = " AND ".join(where) if where else "TRUE"
        limit = max(k * 4, 20)
        vector = self._literal(self.embedder.embed([query])[0])
        columns = (
            "chunk_id,source_type,ref_id,kind,text,process_ids,part_numbers,"
            "data_classification,metadata,embedding::text"
        )
        with self._psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT {columns} FROM {self.table} WHERE {predicate} ORDER BY embedding <=> %s::vector LIMIT %s",
                    (*values, vector, limit),
                )
                dense = cur.fetchall()
                cur.execute(
                    f"SELECT {columns} FROM {self.table} WHERE {predicate} "
                    "AND search_tsv @@ plainto_tsquery('public.mm_unaccent', %s) "
                    "ORDER BY ts_rank(search_tsv, plainto_tsquery('public.mm_unaccent', %s)) DESC "
                    "LIMIT %s",
                    (*values, query, query, limit),
                )
                lexical = cur.fetchall()
        fused: dict[str, float] = {}
        rows = {row[0]: row for row in dense + lexical}
        for ranking in (dense, lexical):
            for rank, row in enumerate(ranking, 1):
                fused[row[0]] = fused.get(row[0], 0) + 1 / (60 + rank)
        result = []
        for chunk_id, score in sorted(fused.items(), key=lambda pair: -pair[1])[:k]:
            row = rows[chunk_id]
            chunk = VectorChunk(
                chunk_id=row[0],
                source_type=row[1],
                ref_id=row[2],
                kind=row[3],
                text=row[4],
                process_ids=row[5],
                part_numbers=row[6],
                data_classification=row[7],
                metadata=row[8],
            )
            result.append(VectorHit(chunk=chunk, score=round(score, 6)))
        return result

    def delete(self, ids: Iterable[str]) -> int:
        identifiers = list(ids)
        if not identifiers:
            return 0
        with self._psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(f"DELETE FROM {self.table} WHERE chunk_id = ANY(%s)", (identifiers,))
                return cur.rowcount
