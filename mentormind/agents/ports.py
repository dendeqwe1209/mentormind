"""What the agents need from spec 05 (retrieval, graph) and spec 07 (Sigma), as Protocols.

The agents only depend on these shapes; the real ``HybridRetriever`` and ``Neo4jGraph`` (spec 05)
and ``CsvSigmaAdapter`` (spec 07) satisfy them structurally, and tests hand in fakes.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from mentormind.knowledge_base.retrieval.hybrid import RetrievedContext, Template
from mentormind.knowledge_base.sigma.adapter import DefectRecord, LotRecord


class Embedder(Protocol):
    """spec 05's text embedder (``BgeM3Embedder``): one vector per text, same model as the index."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class Retriever(Protocol):
    """spec 05 §4 ``HybridRetriever.retrieve``."""

    def retrieve(self, query: str, process_id: str | None = None, k: int = 8) -> RetrievedContext: ...


class GraphTemplates(Protocol):
    """spec 05 §4 Cypher templates, called by name (never free Cypher).

    Every row has ``fact``, ``source_type``, ``ref_id`` and ``data_classification`` (one label or
    the labels of every node the fact is built from). ``ref_id`` is the lot id for
    ``where_symptom_occurred`` and the ``profile_id`` for ``prevention_steps``.
    """

    def run_template(self, template: Template, **params: Any) -> list[dict[str, Any]]: ...

    def match_symptom(self, text: str) -> str | None:
        """``symptom_id`` for free text (spec 05 §4 symptom matching), ``None`` if nothing fits."""
        ...


class CypherRunner(Protocol):
    """spec 05 ``Neo4jGraph.run``: one parameterised Cypher query."""

    def run(self, query: str, **params: Any) -> list[dict[str, Any]]: ...


class ExpertDirectory(Protocol):
    def top_contributor(self, process_id: str) -> str | None:
        """``display_name`` of the expert with the most ``CONTRIBUTED`` steps in the process."""
        ...


class SigmaSource(Protocol):
    """The part of spec 07 ``SigmaAdapter`` the RCA agent reads."""

    def get_lot(self, lot_id: str) -> LotRecord:
        """Raises ``LotNotFound`` for an unknown lot."""
        ...

    def get_defects(self, lot_id: str) -> list[DefectRecord]: ...
