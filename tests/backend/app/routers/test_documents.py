"""spec 08 §2 "Xoá dữ liệu", AC-23 — ``GET /documents`` and ``DELETE /documents/{doc_id}``.

No PostgreSQL: the vector store is the in-memory backend, injected through ``get_vector_store_opener``.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mentormind.backend.app.deps import get_vector_store_opener
from mentormind.backend.app.main import app
from mentormind.backend.app.routers import documents as documents_router
from mentormind.capture.ingest.index import index_files
from mentormind.capture.ingest.jsonl import write_chunks_atomic
from mentormind.capture.ingest.pipeline import doc_id_for
from mentormind.core.config import Settings
from mentormind.core.schemas import ChunkKind, DataClassification, DocumentChunk
from mentormind.knowledge_base.store.vector_store import MemoryVectorStore, VectorStoreError


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, work_dir=tmp_path / "work")


@pytest.fixture
def vectors() -> MemoryVectorStore:
    return MemoryVectorStore()


@pytest.fixture
def client(settings: Settings, vectors: MemoryVectorStore, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(documents_router, "get_settings", lambda: settings)
    app.dependency_overrides[get_vector_store_opener] = lambda: lambda: vectors
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _ingested(settings: Settings, vectors: MemoryVectorStore, job_id: str, name: str, label: DataClassification) -> str:
    """An upload as ``POST /ingest/documents`` leaves it: the copy, two chunks on file and indexed."""
    upload = settings.work_dir / "docs" / job_id / name
    upload.parent.mkdir(parents=True, exist_ok=True)
    upload.write_bytes(b"%PDF-1.7 " + name.encode())
    doc_id = doc_id_for(upload)
    chunks = [
        DocumentChunk(
            chunk_id=f"{doc_id}#p{page}-0",
            doc_id=doc_id,
            source_path=str(upload),
            title="SOP đóng gói",
            page=page,
            kind=ChunkKind.TEXT,
            text=f"Công đoạn PACK01 trang {page} của {name}",
            data_classification=label,
            extractor="docling",
        )
        for page in (1, 2)
    ]
    chunk_file = settings.work_dir / "chunks" / f"{doc_id}.jsonl"
    write_chunks_atomic(chunk_file, chunks)
    assert index_files([chunk_file], vectors).upserted == 2
    return doc_id


def _hits(vectors: MemoryVectorStore, doc_id: str) -> int:
    return len(vectors.search("PACK01", k=10, filters={"doc_id": doc_id}))


def test_ac_23_documents_are_listed_from_their_chunk_files(
    client: TestClient, settings: Settings, vectors: MemoryVectorStore
) -> None:
    assert client.get("/documents").json() == []  # nothing ingested yet
    sop = _ingested(settings, vectors, "job-doc-1", "sop.pdf", DataClassification.SYNTHETIC)
    bom = _ingested(settings, vectors, "job-doc-2", "bom.xlsx", DataClassification.PUBLIC)
    listed: list[dict[str, Any]] = client.get("/documents").json()
    assert [(d["doc_id"], d["name"], d["data_classification"], d["chunks"]) for d in listed] == [
        (bom, "bom.xlsx", "public", 2),
        (sop, "sop.pdf", "synthetic", 2),
    ]
    assert listed[0]["title"] == "SOP đóng gói" and listed[0]["extractor"] == "docling"


def test_ac_23_deleting_a_document_removes_its_chunks_and_files_only(
    client: TestClient, settings: Settings, vectors: MemoryVectorStore
) -> None:
    sop = _ingested(settings, vectors, "job-doc-1", "sop.pdf", DataClassification.SYNTHETIC)
    again = _ingested(settings, vectors, "job-doc-3", "sop.pdf", DataClassification.SYNTHETIC)  # same bytes
    bom = _ingested(settings, vectors, "job-doc-2", "bom.xlsx", DataClassification.PUBLIC)
    assert again == sop
    res = client.delete(f"/documents/{sop}")
    assert res.status_code == 200, res.text
    assert res.json() == {"doc_id": sop, "chunks_deleted": 2, "chunk_file_removed": True, "uploads_removed": 2}
    assert _hits(vectors, sop) == 0 and _hits(vectors, bom) == 2
    assert not (settings.work_dir / "chunks" / f"{sop}.jsonl").exists()
    docs = settings.work_dir / "docs"
    assert sorted(p.name for p in docs.iterdir()) == ["job-doc-2"]  # emptied upload folders are gone
    assert [d["doc_id"] for d in client.get("/documents").json()] == [bom]


@pytest.mark.parametrize("doc_id", ["DOC-000000000000", "DOC-xyz", "DOC-AAAAAAAAAAAA", "sop.pdf"])
def test_ac_23_unknown_or_malformed_doc_id_is_404(
    client: TestClient, settings: Settings, vectors: MemoryVectorStore, doc_id: str
) -> None:
    _ingested(settings, vectors, "job-doc-1", "sop.pdf", DataClassification.SYNTHETIC)
    assert client.delete(f"/documents/{doc_id}").status_code == 404
    assert len(client.get("/documents").json()) == 1


def test_ac_23_vector_store_down_is_503_and_nothing_is_removed(
    client: TestClient, settings: Settings, vectors: MemoryVectorStore
) -> None:
    sop = _ingested(settings, vectors, "job-doc-1", "sop.pdf", DataClassification.SYNTHETIC)

    def down() -> MemoryVectorStore:
        raise VectorStoreError("Không kết nối được PostgreSQL")

    app.dependency_overrides[get_vector_store_opener] = lambda: down
    res = client.delete(f"/documents/{sop}")
    assert res.status_code == 503 and "PostgreSQL" in res.json()["detail"]
    assert (settings.work_dir / "chunks" / f"{sop}.jsonl").is_file()
    assert (settings.work_dir / "docs" / "job-doc-1" / "sop.pdf").is_file() and _hits(vectors, sop) == 2
