"""``VectorStore`` on PostgreSQL + pgvector (spec 02b §5; table of ``infra/postgres/init.sql`` §9b).

Search is hybrid like the memory backend: cosine distance on ``embedding`` plus full-text on
``search_tsv`` (accent-folded), fused by Reciprocal Rank Fusion, all in one SQL statement.
Filter columns come from :func:`parse_filters`' whitelist and every value is a bound parameter,
so no caller text reaches the SQL string.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from mentormind.core.schemas.vector import VectorChunk, VectorHit
from mentormind.knowledge_base.store.vector_store import (
    RRF_K,
    Embedder,
    FilterClause,
    VectorStoreError,
    embed_missing,
    parse_filters,
    require_filters,
    tokens,
)

_TABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
_MIN_POOL = 50
_POOL_PER_HIT = 5
_COLUMNS = (
    "chunk_id",
    "source_type",
    "ref_id",
    "kind",
    "text",
    "process_ids",
    "part_numbers",
    "data_classification",
    "metadata",
)


def quote_table(name: str) -> sql.Identifier:
    """The table as a quoted identifier.

    Raises:
        VectorStoreError: ``name`` is not a plain identifier (no schema prefix, no punctuation).
    """
    if not _TABLE_NAME.match(name):
        raise VectorStoreError(f"KNOWHOW_VECTOR_TABLE không hợp lệ: {name!r} (chỉ chữ, số, gạch dưới).")
    return sql.Identifier(name)


def vector_literal(vector: Sequence[float]) -> str:
    """pgvector text form, cast with ``::vector`` so no extra Python package is needed."""
    return "[" + ",".join(repr(float(v)) for v in vector) + "]"


def check_dimension(declared: int, expected: int) -> None:
    """Compare the table's ``vector(N)`` with the embedder's dimension (spec 02b AC-16).

    Raises:
        VectorStoreError: they differ, or the column has no fixed dimension.
    """
    if declared < 0:
        raise VectorStoreError("Cột embedding không khai báo số chiều (cần vector(N)).")
    if declared != expected:
        raise VectorStoreError(
            f"Bảng khai báo vector({declared}) nhưng embedder sinh {expected} chiều; "
            "chỉnh KNOWHOW_EMBED_DIM hoặc init.sql cho khớp."
        )


def build_where(clauses: Sequence[FilterClause]) -> tuple[sql.Composable, dict[str, Any]]:
    """AND of the clauses; columns are whitelisted identifiers, values are named parameters."""
    if not clauses:
        return sql.SQL("TRUE"), {}
    parts: list[sql.Composable] = []
    params: dict[str, Any] = {}
    for i, clause in enumerate(clauses):
        if not clause.values:  # "any of nothing" matches nothing: fail closed
            parts.append(sql.SQL("FALSE"))
            continue
        name = f"f{i}"
        params[name] = clause.values
        column = sql.Identifier(clause.column)
        if clause.is_array:
            parts.append(sql.SQL("{} && %({})s::text[]").format(column, sql.SQL(name)))
        elif clause.column == "data_classification":  # a domain over text
            parts.append(sql.SQL("{}::text = ANY(%({})s)").format(column, sql.SQL(name)))
        else:
            parts.append(sql.SQL("{} = ANY(%({})s)").format(column, sql.SQL(name)))
    return sql.SQL(" AND ").join(parts), params


class PgVectorStore:
    """One short-lived connection per call; ``upsert`` and ``delete`` are each one transaction."""

    def __init__(self, dsn: str, table: str, embedder: Embedder, *, verify: bool = True) -> None:
        self._dsn = dsn
        self._table = quote_table(table)
        self._table_name = table
        self._embedder = embedder
        if verify:
            self.verify()

    def verify(self) -> None:
        """Check the table exists and its ``vector(N)`` matches the embedder.

        Raises:
            VectorStoreError: the database is unreachable, the table is missing, or N differs.
        """
        try:
            with psycopg.connect(self._dsn) as conn:
                row = conn.execute(
                    "SELECT a.atttypmod FROM pg_attribute a "
                    "WHERE a.attrelid = to_regclass(%s) AND a.attname = 'embedding' AND NOT a.attisdropped",
                    (self._table_name,),
                ).fetchone()
        except psycopg.OperationalError as exc:
            raise VectorStoreError(f"Không kết nối được PostgreSQL ({exc}); đã chạy `make up` chưa?") from exc
        if row is None:
            raise VectorStoreError(f"Không thấy bảng {self._table_name}.embedding; chạy infra/postgres/init.sql.")
        check_dimension(int(row[0]), self._embedder.dim)

    def upsert(self, chunks: Iterable[VectorChunk]) -> int:
        batch = embed_missing(chunks, self._embedder)
        if not batch:
            return 0
        columns = sql.SQL(", ").join(sql.Identifier(c) for c in (*_COLUMNS, "embedding"))
        values = sql.SQL("%s, %s, %s, %s, %s, %s::text[], %s::text[], %s, %s, %s::vector")
        updates = sql.SQL(", ").join(
            sql.SQL("{0} = EXCLUDED.{0}").format(sql.Identifier(c)) for c in (*_COLUMNS[1:], "embedding")
        )
        statement = sql.SQL(
            "INSERT INTO {table} ({columns}) VALUES ({values}) "
            "ON CONFLICT (chunk_id) DO UPDATE SET {updates}, updated_at = now()"
        ).format(table=self._table, columns=columns, values=values, updates=updates)
        rows = [
            (
                c.chunk_id,
                c.source_type,
                c.ref_id,
                c.kind,
                c.text,
                c.process_ids,
                c.part_numbers,
                c.data_classification.value,
                Jsonb(c.metadata),
                vector_literal(c.embedding or []),
            )
            for c in batch
        ]
        with psycopg.connect(self._dsn) as conn, conn.cursor() as cur:
            cur.executemany(statement, rows)
        return len(batch)

    def search(self, query: str, k: int = 8, filters: Mapping[str, Any] | None = None) -> list[VectorHit]:
        if k <= 0:
            return []
        where, params = build_where(parse_filters(filters or {}))
        pool = max(k * _POOL_PER_HIT, _MIN_POOL)
        params.update(q=vector_literal(self._embedder.embed([query])[0]), pool=pool, k=k)
        terms = tokens(query)  # \w+ only: safe to build a tsquery from
        lexical = sql.SQL("")
        union = sql.SQL("SELECT chunk_id, r FROM dense")
        if terms:
            params["tsq"] = " | ".join(terms)
            lexical = sql.SQL(
                ", lex AS (SELECT chunk_id, row_number() OVER (ORDER BY rank DESC, chunk_id) AS r FROM ("
                "SELECT f.chunk_id, ts_rank(f.search_tsv, q) AS rank FROM filtered f, "
                "to_tsquery('public.mm_unaccent'::regconfig, %(tsq)s) q WHERE f.search_tsv @@ q "
                "ORDER BY rank DESC, f.chunk_id LIMIT %(pool)s) ranked)"
            )
            union = sql.SQL("SELECT chunk_id, r FROM dense UNION ALL SELECT chunk_id, r FROM lex")
        statement = sql.SQL(
            "WITH filtered AS (SELECT chunk_id, embedding, search_tsv FROM {table} "
            "WHERE embedding IS NOT NULL AND {where}), "
            "dense AS (SELECT chunk_id, row_number() OVER (ORDER BY embedding <=> %(q)s::vector, chunk_id) AS r "
            "FROM filtered ORDER BY embedding <=> %(q)s::vector, chunk_id LIMIT %(pool)s)"
            "{lexical}, "
            "fused AS (SELECT chunk_id, sum(1.0 / ({rrf} + r)) AS score FROM ({union}) u GROUP BY chunk_id) "
            "SELECT {columns}, f.score FROM fused f JOIN {table} c USING (chunk_id) "
            "ORDER BY f.score DESC, c.chunk_id LIMIT %(k)s"
        ).format(
            table=self._table,
            where=where,
            lexical=lexical,
            rrf=sql.Literal(RRF_K),
            union=union,
            columns=sql.SQL(", ").join(
                sql.SQL("c.{}{}").format(sql.Identifier(c), sql.SQL("::text" if c == "data_classification" else ""))
                for c in _COLUMNS
            ),
        )
        with psycopg.connect(self._dsn) as conn:
            rows = conn.execute(statement, params).fetchall()
        return [VectorHit(chunk=_to_chunk(row[:-1]), score=round(float(row[-1]), 6)) for row in rows]

    def delete(self, ids: Iterable[str]) -> int:
        wanted = list(ids)
        if not wanted:
            return 0
        statement = sql.SQL("DELETE FROM {table} WHERE chunk_id = ANY(%s)").format(table=self._table)
        with psycopg.connect(self._dsn) as conn, conn.cursor() as cur:
            cur.execute(statement, (wanted,))
            return cur.rowcount

    def delete_where(self, filters: Mapping[str, Any]) -> int:
        where, params = build_where(require_filters(filters))
        statement = sql.SQL("DELETE FROM {table} WHERE {where}").format(table=self._table, where=where)
        with psycopg.connect(self._dsn) as conn, conn.cursor() as cur:
            cur.execute(statement, params)
            return cur.rowcount


def _to_chunk(row: Sequence[Any]) -> VectorChunk:
    chunk_id, source_type, ref_id, kind, text, process_ids, part_numbers, label, metadata = row
    return VectorChunk(
        chunk_id=chunk_id,
        source_type=source_type,
        ref_id=ref_id,
        text=text,
        kind=kind,
        process_ids=process_ids,
        part_numbers=part_numbers,
        data_classification=label,
        metadata=metadata,
    )
