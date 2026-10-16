"""Wire the agents to the real spec 05 / spec 07 components (spec 06 FR-03).

The graph, vector store and Sigma modules are imported when an agent is built, so a missing extra
(``kg``) stops the command with a clear message instead of breaking ``knowhow --help``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, cast

from mentormind.agents.adapters.experts import GraphExperts
from mentormind.agents.base import TraceLog
from mentormind.agents.ports import Embedder
from mentormind.agents.rca import RcaAgent
from mentormind.agents.work_assistant import WorkAssistant
from mentormind.core.config import Settings
from mentormind.core.providers.llm import get_llm_provider
from mentormind.core.schemas import DataClassification

T = TypeVar("T")


class AgentWiringError(RuntimeError):
    """A component the agent needs is missing or not configured."""


def build_work_assistant(settings: Settings) -> WorkAssistant:
    try:
        from mentormind.knowledge_base.retrieval.hybrid import get_hybrid_retriever
    except ImportError as exc:
        raise AgentWiringError(f"Thiếu thư viện của spec 05 ({exc.name}): uv sync --extra kg.") from exc
    retriever = _graph_backed(get_hybrid_retriever, settings)
    return WorkAssistant(
        retriever,
        get_llm_provider(settings),
        embedder=_embedder(retriever, settings),
        experts=GraphExperts(retriever.graph),
        min_score=settings.assist_min_score,
        min_cosine=settings.assist_min_cosine,
        trace=TraceLog(settings.trace_dir),
    )


def _embedder(retriever: Any, settings: Settings) -> Embedder:
    """The vector store's own embedder when it has one (one ~2 GB model in memory), else the configured one.

    ``PgVectorStore`` keeps it as ``_embedder`` (``store/pgvector_store.py``), older stores as ``embedder``.
    Otherwise ``KNOWHOW_EMBEDDER`` decides (bge-m3 here, or on the inference server).
    """
    vectors = getattr(retriever, "vectors", None)
    for name in ("embedder", "_embedder"):
        shared = getattr(vectors, name, None)
        if shared is not None:
            return cast(Embedder, shared)
    from mentormind.knowledge_base.store.vector_store import get_embedder

    return get_embedder(settings)


def build_rca_agent(settings: Settings) -> RcaAgent:
    try:
        from mentormind.knowledge_base.kg.client import Neo4jGraph
        from mentormind.knowledge_base.retrieval.hybrid import HybridRetriever
        from mentormind.knowledge_base.store.vector_store import get_vector_store
    except ImportError as exc:
        raise AgentWiringError(f"Thiếu thư viện của spec 05 ({exc.name}): uv sync --extra kg.") from exc
    # No router: the RCA agent calls the templates by name itself (spec 06 AC-08).
    graph = _graph_backed(Neo4jGraph, settings)
    knowledge = HybridRetriever(get_vector_store(settings), graph, router=None)
    # The CSV adapter reads the synthetic mock of spec 07 §3; any real Sigma is factory data.
    mock = settings.sigma_adapter == "csv"
    return RcaAgent(
        get_llm_provider(settings),
        knowledge,
        knowledge,
        _sigma(settings),
        sigma_classification=(DataClassification.SYNTHETIC if mock else DataClassification.FACTORY_CONFIDENTIAL),
        trace=TraceLog(settings.trace_dir),
    )


def _graph_backed(build: Callable[[Settings], T], settings: Settings) -> T:
    try:
        return build(settings)
    except RuntimeError as exc:  # Neo4jGraph without the neo4j driver installed
        raise AgentWiringError(str(exc)) from exc


def _sigma(settings: Settings) -> Any:
    from mentormind.knowledge_base.sigma.adapter import CsvSigmaAdapter

    if settings.sigma_adapter != "csv":
        raise AgentWiringError(f"Chưa có Sigma adapter {settings.sigma_adapter!r} (spec 07).")
    return CsvSigmaAdapter(settings.sigma_csv_dir)
