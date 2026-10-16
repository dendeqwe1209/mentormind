"""spec 02 FR-07d / AC-20, AC-21 — bge-m3 on the team's inference server (``KNOWHOW_EMBEDDER=remote``).

The server is a ``httpx.MockTransport`` (constitution art. 6: no network in tests).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import httpx
import pytest

from mentormind.capture.ingest.index import index_files
from mentormind.capture.ingest.jsonl import write_chunks_atomic
from mentormind.core.config import Settings
from mentormind.core.guard import ConfidentialDataError
from mentormind.core.schemas import ChunkKind, DataClassification, DocumentChunk
from mentormind.core.schemas.vector import VectorChunk
from mentormind.knowledge_base.store.embedder import RemoteEmbedder
from mentormind.knowledge_base.store.vector_store import (
    HashingEmbedder,
    MemoryVectorStore,
    VectorStoreError,
    get_embedder,
    get_vector_store,
)
from tests.core.providers.inference.fakes import PRIVATE_URL, PUBLIC_URL, FakeInferenceServer

CONFIDENTIAL = DataClassification.FACTORY_CONFIDENTIAL


def embeddings(request: httpx.Request) -> httpx.Response:
    """bge-m3 stand-in: text "t<i>" -> [i + 1, 1] (not unit length), rows in reverse order."""
    texts = json.loads(request.content)["input"]
    rows = [{"index": i, "embedding": [_number(t) + 1, 1.0]} for i, t in enumerate(texts)]
    return httpx.Response(200, json={"object": "list", "data": rows[::-1], "model": "BAAI/bge-m3"})


def _number(text: str) -> float:
    return float(text[1:]) if text[1:].isdigit() else float(len(text))


def remote(url: str = PRIVATE_URL, *, dim: int = 2, **kw: Any) -> tuple[RemoteEmbedder, FakeInferenceServer]:
    server = FakeInferenceServer({"/embeddings": embeddings})
    return RemoteEmbedder(server.client(url, **kw), dim=dim), server


def vchunk(cid: str, text: str, label: DataClassification) -> VectorChunk:
    return VectorChunk(chunk_id=cid, source_type="document", ref_id=cid, text=text, data_classification=label)


def test_ac_20_batches_of_32_in_input_order_unit_length() -> None:
    embedder, server = remote()
    texts = [f"t{i}" for i in range(70)]
    vectors = embedder.embed_classified(texts, "public")
    sent = [json.loads(r.content) for r in server.requests]
    assert [len(body["input"]) for body in sent] == [32, 32, 6]
    assert all(body["model"] == "BAAI/bge-m3" for body in sent)
    assert [str(r.url) for r in server.requests] == [f"{PRIVATE_URL}/embeddings"] * 3
    for i, vector in enumerate(vectors):  # row order restored from "index", then L2-normalised
        norm = math.hypot(i + 1, 1.0)
        assert vector == pytest.approx([(i + 1) / norm, 1 / norm])
        assert math.isclose(sum(x * x for x in vector), 1.0)
    assert embedder.dim == 2 and embedder.embed_classified([], "public") == []


def test_ac_20_wrong_dimension_count_or_server_failure_is_a_vector_store_error() -> None:
    wrong_dim, _ = remote(dim=1024)
    with pytest.raises(VectorStoreError, match=r"2 chiều.*1024"):
        wrong_dim.embed_classified(["t1"], "public")
    short = FakeInferenceServer({"/embeddings": {"data": [{"index": 0, "embedding": [1.0, 0.0]}]}})
    with pytest.raises(VectorStoreError, match="1 vector cho 2"):
        RemoteEmbedder(short.client(), dim=2).embed_classified(["a", "b"], "public")
    down = FakeInferenceServer({"/embeddings": httpx.Response(400, text="bad input")})
    with pytest.raises(VectorStoreError, match="bad input"):
        RemoteEmbedder(down.client(), dim=2).embed_classified(["a"], "public")


def test_ac_21_cloud_url_never_receives_confidential_text_or_questions() -> None:
    embedder, server = remote(PUBLIC_URL)
    assert embedder.is_cloud is True
    with pytest.raises(ConfidentialDataError):
        embedder.embed_classified(["bí mật nhà máy"], CONFIDENTIAL)
    with pytest.raises(ConfidentialDataError):  # unlabelled text (a question) counts as confidential
        embedder.embed(["câu hỏi của công nhân"])
    assert server.requests == []
    assert len(embedder.embed_classified(["t1"], DataClassification.SYNTHETIC)) == 1
    declared, _ = remote(PUBLIC_URL, local_hosts=["inference.example.com"])
    assert declared.is_cloud is False and len(declared.embed(["câu hỏi"])) == 1


def test_ac_21_the_store_passes_the_chunk_label_before_anything_is_sent() -> None:
    embedder, server = remote(PUBLIC_URL)
    store = MemoryVectorStore(embedder)
    assert store.upsert([vchunk("p", "t1", DataClassification.PUBLIC)]) == 1
    with pytest.raises(ConfidentialDataError):
        store.upsert([vchunk("s", "t2", DataClassification.SYNTHETIC), vchunk("c", "t3", CONFIDENTIAL)])
    with pytest.raises(ConfidentialDataError):  # the search query is unlabelled: strictest
        store.search("t1")
    assert len(server.requests) == 1  # only the public upsert went out
    local, _ = remote()
    private_store = MemoryVectorStore(local)
    private_store.upsert([vchunk("c", "t3", CONFIDENTIAL)])
    assert [h.chunk.chunk_id for h in private_store.search("t3")] == ["c"]


def test_ac_21_ingest_index_fails_only_the_confidential_file(tmp_path: Path) -> None:
    def chunk(doc: str, label: DataClassification) -> DocumentChunk:
        return DocumentChunk(
            chunk_id=f"DOC-{doc * 12}#p1-0",
            doc_id=f"DOC-{doc * 12}",
            source_path=f"{doc}.pdf",
            title=None,
            page=1,
            kind=ChunkKind.TEXT,
            text="t1",
            data_classification=label,
            extractor="docling",
        )

    write_chunks_atomic(tmp_path / "a.jsonl", [chunk("a", DataClassification.PUBLIC)])
    write_chunks_atomic(tmp_path / "b.jsonl", [chunk("b", CONFIDENTIAL)])
    embedder, server = remote(PUBLIC_URL)
    result = index_files(sorted(tmp_path.glob("*.jsonl")), MemoryVectorStore(embedder))
    assert (result.upserted, result.files_ok) == (1, 1)
    [(name, why)] = result.files_failed
    assert name == "b.jsonl" and "factory_confidential" in why
    assert len(server.requests) == 1


def test_ac_20_settings_select_the_remote_embedder(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(VectorStoreError, match="KNOWHOW_INFERENCE_URL"):
        get_embedder(Settings(_env_file=None, embedder="remote", inference_url=None))
    settings = Settings(_env_file=None, embedder="remote", inference_url=PRIVATE_URL, embed_dim=1024)
    embedder = get_embedder(settings)
    assert isinstance(embedder, RemoteEmbedder) and embedder.dim == 1024 and embedder.is_cloud is False
    assert isinstance(get_embedder(Settings(_env_file=None, embedder="hashing", embed_dim=8)), HashingEmbedder)

    from mentormind.knowledge_base.store import pgvector_store

    seen: list[object] = []
    monkeypatch.setattr(
        pgvector_store.PgVectorStore, "__init__", lambda self, dsn, table, embedder, **kw: seen.append(embedder)
    )
    get_vector_store(settings.model_copy(update={"vector_backend": "pgvector"}))
    assert isinstance(seen[0], RemoteEmbedder)


def test_ac_20_the_work_assistant_falls_back_to_the_configured_embedder(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from mentormind.agents.adapters import factory
    from mentormind.knowledge_base.retrieval import hybrid

    retriever = SimpleNamespace(vectors=SimpleNamespace(), graph=SimpleNamespace(run=lambda *a, **k: []))
    monkeypatch.setattr(hybrid, "get_hybrid_retriever", lambda settings: retriever)
    settings = Settings(
        _env_file=None, llm_provider="fake", trace_dir=None, embedder="remote", inference_url=PRIVATE_URL
    )
    assert isinstance(factory.build_work_assistant(settings).embedder, RemoteEmbedder)
