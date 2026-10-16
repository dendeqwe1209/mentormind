"""spec 06 FR-03 — the agents wired to the real spec 05 / spec 07 components."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mentormind.agents.adapters import factory
from mentormind.agents.adapters.experts import TOP_CONTRIBUTOR, GraphExperts
from mentormind.core.config import Settings
from mentormind.knowledge_base.kg import client
from mentormind.knowledge_base.retrieval.hybrid import HybridRetriever
from mentormind.knowledge_base.sigma.adapter import CsvSigmaAdapter
from mentormind.knowledge_base.store import vector_store


class FakeCypher:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        self.calls.append((query, params))
        return self.rows


def test_ac_08_the_rca_agent_gets_a_retriever_without_router(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    graph = FakeCypher([])
    monkeypatch.setattr(client, "Neo4jGraph", lambda settings: graph)
    monkeypatch.setattr(vector_store, "get_vector_store", lambda settings: object())
    settings = Settings(llm_provider="fake", sigma_csv_dir=tmp_path, trace_dir=None)
    agent = factory.build_rca_agent(settings)
    assert isinstance(agent.retriever, HybridRetriever) and agent.retriever.router is None
    assert agent.graph is agent.retriever and agent.retriever.graph is graph
    assert isinstance(agent.sigma, CsvSigmaAdapter) and agent.sigma.directory == tmp_path


def test_only_the_csv_sigma_exists_yet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client, "Neo4jGraph", lambda settings: FakeCypher([]))
    monkeypatch.setattr(vector_store, "get_vector_store", lambda settings: object())
    with pytest.raises(factory.AgentWiringError, match="spec 07"):
        factory.build_rca_agent(Settings(llm_provider="fake", sigma_adapter="mes"))


def test_the_expert_to_ask_is_the_top_contributor_of_the_process() -> None:
    graph = FakeCypher([{"name": "Anh Tuấn", "steps": 4}])
    assert GraphExperts(graph).top_contributor("PACK01") == "Anh Tuấn"
    assert graph.calls == [(TOP_CONTRIBUTOR, {"process_id": "PACK01"})]
    assert GraphExperts(FakeCypher([])).top_contributor("PACK01") is None


@pytest.mark.parametrize("attribute", ["embedder", "_embedder"])  # _embedder: store/pgvector_store.py
def test_the_work_assistant_reuses_the_vector_store_embedder(monkeypatch: pytest.MonkeyPatch, attribute: str) -> None:
    from types import SimpleNamespace

    from mentormind.knowledge_base.retrieval import hybrid

    shared = object()  # bge-m3 is ~2 GB: one copy in memory, shared with spec 05's index
    retriever = SimpleNamespace(vectors=SimpleNamespace(**{attribute: shared}), graph=FakeCypher([]))
    monkeypatch.setattr(hybrid, "get_hybrid_retriever", lambda settings: retriever)
    settings = Settings(llm_provider="fake", trace_dir=None, assist_min_score=0.03, assist_min_cosine=0.5)
    assistant = factory.build_work_assistant(settings)
    assert assistant.embedder is shared
    assert (assistant.min_score, assistant.min_cosine) == (0.03, 0.5)
