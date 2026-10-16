"""Small parameterized Neo4j client; driver imported only when a live graph is requested."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

from mentormind.core.config import Settings, get_settings

SCHEMA = Path(__file__).with_name("schema.cypher")


class Neo4jGraph:
    def __init__(self, settings: Settings | None = None):
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise RuntimeError("Install the kg extra: uv sync --extra kg") from exc
        settings = settings or get_settings()
        self._driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
        )
        self._transaction: Any = None

    def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        if self._transaction is not None:
            return [dict(record) for record in self._transaction.run(query, **params)]
        with self._driver.session() as session:
            return [dict(record) for record in session.run(query, **params)]

    @contextmanager
    def transaction(self) -> Iterator[None]:
        if self._transaction is not None:
            raise RuntimeError("Nested graph transaction")
        with self._driver.session() as session:
            transaction = session.begin_transaction()
            self._transaction = transaction
            try:
                yield
                transaction.commit()
            except Exception:
                with suppress(Exception):
                    transaction.rollback()
                raise
            finally:
                self._transaction = None

    def init(self) -> None:
        for statement in SCHEMA.read_text(encoding="utf-8").split(";"):
            if statement.strip():
                self.run(statement.strip())

    def close(self) -> None:
        self._driver.close()
