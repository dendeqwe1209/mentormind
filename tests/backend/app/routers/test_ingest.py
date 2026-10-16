"""spec 08 §2, AC-09..AC-12 — ``POST /ingest/documents`` runs spec 02 ``ingest run`` + index.

No Docling, no bge-m3, no database: the job's builders are swapped for the spec 02 fake extractor,
a whitespace token counter and an in-memory vector store. ``TestClient`` runs the background job
before ``post`` returns, so the job is finished when it is read back.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mentormind.backend.app.deps import get_profile_store
from mentormind.backend.app.main import app
from mentormind.backend.app.routers import ingest as ingest_router
from mentormind.capture.ingest import cli as ingest_cli
from mentormind.capture.ingest.extractors.base import ExtractorError
from mentormind.capture.ingest.jsonl import write_chunks_atomic
from mentormind.capture.ingest.raw import RawBlock, RawDocument
from mentormind.capture.ingest.tokens import WhitespaceTokenCounter
from mentormind.core.config import Settings
from mentormind.core.schemas import ChunkKind, DataClassification, DocumentChunk
from mentormind.core.schemas.vector import VectorChunk
from mentormind.knowledge_base.store.profile_store import ProfileStore
from mentormind.knowledge_base.store.vector_store import MemoryVectorStore
from tests.capture.ingest.fakes import FakeExtractor

OFFICE = (".pdf", ".docx", ".xlsx", ".pptx")
# Two pages -> two chunks: a text block and a table.
DOC = RawDocument(
    path="sop.pdf",
    num_pages=2,
    extractor="docling",
    blocks=[
        RawBlock(kind=ChunkKind.TEXT, text="Công đoạn PACK01: xếp linh kiện vào hộp.", page=1),
        RawBlock(kind=ChunkKind.TABLE, text="| bước | việc |\n| --- | --- |\n| 1 | PACK01 |", page=2),
    ],
)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, work_dir=tmp_path / "work")


@pytest.fixture
def vectors() -> MemoryVectorStore:
    return MemoryVectorStore()


@pytest.fixture
def jobs(tmp_path: Path) -> ProfileStore:
    return ProfileStore(db_path=tmp_path / "profiles.sqlite")


@pytest.fixture
def client(
    settings: Settings, vectors: MemoryVectorStore, jobs: ProfileStore, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setattr(ingest_router, "get_settings", lambda: settings)
    monkeypatch.setattr(ingest_cli, "build_extractors", lambda s: [FakeExtractor("docling", suffixes=OFFICE, doc=DOC)])
    monkeypatch.setattr(ingest_cli, "build_counter", lambda s: WhitespaceTokenCounter())
    monkeypatch.setattr(ingest_cli, "build_store", lambda s: vectors)
    app.dependency_overrides[get_profile_store] = lambda: jobs
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _upload(client: TestClient, *names: str, classification: str | None = "synthetic") -> Any:
    # Different bytes per file, so every file gets its own doc_id.
    files = [("files", (name, b"%PDF-1.7 " + name.encode(), "application/pdf")) for name in names]
    data = {} if classification is None else {"classification": classification}
    return client.post("/ingest/documents", files=files, data=data)


def _job(client: TestClient, response: Any) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    job: dict[str, Any] = client.get(f"/jobs/{response.json()['job_id']}").json()
    return job


def _job_count(jobs: ProfileStore) -> int:
    with closing(sqlite3.connect(jobs.db_path)) as conn:
        count: int = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    return count


def test_ac_09_uploaded_file_is_ingested_and_its_chunks_indexed(
    client: TestClient, settings: Settings, vectors: MemoryVectorStore
) -> None:
    job = _job(client, _upload(client, "sop.pdf", classification="synthetic"))
    assert job["status"] == "done", job
    [entry] = job["result"]["files"]
    assert entry["name"] == "sop.pdf" and entry["doc_id"].startswith("DOC-")
    assert (entry["extractor"], entry["pages"], entry["chunks"]) == ("docling", 2, 2)
    assert (entry["skipped"], entry["error"]) == (False, None)
    assert (job["result"]["classification"], job["result"]["chunks_indexed"]) == ("synthetic", 2)
    hits = vectors.search("PACK01", k=10, filters={"doc_id": entry["doc_id"]})
    assert len(hits) == 2 and {h.chunk.data_classification for h in hits} == {DataClassification.SYNTHETIC}
    # Same folder as `knowhow ingest run`, so `knowhow ingest index` still sees the chunks.
    assert (settings.work_dir / "chunks" / f"{entry['doc_id']}.jsonl").is_file()


def test_ac_09_only_the_chunks_of_this_upload_are_indexed(
    client: TestClient, settings: Settings, vectors: MemoryVectorStore
) -> None:
    earlier = DocumentChunk(
        chunk_id="DOC-aaaaaaaaaaaa#p1-0",
        doc_id="DOC-aaaaaaaaaaaa",
        source_path="old.pdf",
        kind=ChunkKind.TEXT,
        text="bản cũ PACK01",
        data_classification=DataClassification.PUBLIC,
        extractor="docling",
    )
    write_chunks_atomic(settings.work_dir / "chunks" / "DOC-aaaaaaaaaaaa.jsonl", [earlier])
    job = _job(client, _upload(client, "sop.pdf"))
    assert job["status"] == "done" and job["result"]["chunks_indexed"] == 2
    assert vectors.search("PACK01", k=10, filters={"doc_id": "DOC-aaaaaaaaaaaa"}) == []


@pytest.mark.parametrize("name", ["../../evil.pdf", "..\\..\\evil.pdf", "{tmp}/evil.pdf"])
def test_ac_10_file_is_stored_under_the_upload_dir_by_its_base_name(
    client: TestClient, settings: Settings, tmp_path: Path, name: str
) -> None:
    response = _upload(client, name.format(tmp=tmp_path))
    job = _job(client, response)
    upload_dir = settings.work_dir / "docs" / response.json()["job_id"]
    assert sorted(tmp_path.rglob("evil.pdf")) == [upload_dir / "evil.pdf"]
    assert job["status"] == "done" and job["result"]["files"][0]["name"] == "evil.pdf"


@pytest.mark.parametrize("names", [[""], [".."], ["docs/.."], ["a.pdf", "copy/a.pdf"]])
def test_empty_dot_or_duplicate_file_names_are_rejected(
    client: TestClient, settings: Settings, jobs: ProfileStore, names: list[str]
) -> None:
    assert _upload(client, *names).status_code == 422
    assert not (settings.work_dir / "docs").exists() and _job_count(jobs) == 0


@pytest.mark.parametrize("classification", [None, "secret"])
def test_ac_11_missing_or_unknown_classification_is_422_and_nothing_is_kept(
    client: TestClient, settings: Settings, jobs: ProfileStore, classification: str | None
) -> None:
    assert _upload(client, "sop.pdf", classification=classification).status_code == 422
    assert not (settings.work_dir / "docs").exists() and _job_count(jobs) == 0


def test_ac_12_no_file_ingested_fails_the_job_and_the_server_keeps_serving(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = FakeExtractor("docling", suffixes=OFFICE, raises=ExtractorError("tệp hỏng"))
    monkeypatch.setattr(ingest_cli, "build_extractors", lambda s: [broken])
    job = _job(client, _upload(client, "a.pdf", "notes.txt"))
    assert job["status"] == "failed"
    assert "a.pdf" in job["error"] and "tệp hỏng" in job["error"] and "notes.txt" in job["error"]
    by_name = {f["name"]: f for f in job["result"]["files"]}
    assert "tệp hỏng" in by_name["a.pdf"]["error"] and by_name["notes.txt"]["skipped"]
    assert job["result"]["chunks_indexed"] == 0
    assert client.get("/health").status_code == 200


def test_ac_12_index_raising_fails_the_job_and_the_server_keeps_serving(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class DownStore(MemoryVectorStore):
        def upsert(self, chunks: Iterable[VectorChunk]) -> int:
            raise RuntimeError("pgvector không phản hồi")

    monkeypatch.setattr(ingest_cli, "build_store", lambda s: DownStore())
    job = _job(client, _upload(client, "sop.pdf"))
    assert job["status"] == "failed" and "pgvector không phản hồi" in job["error"]
    assert job["result"]["files"][0]["chunks"] == 2 and job["result"]["chunks_indexed"] == 0
    assert client.get("/health").status_code == 200


def test_one_failing_file_does_not_stop_the_others(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, vectors: MemoryVectorStore
) -> None:
    class Flaky(FakeExtractor):
        def extract(self, path: Path) -> RawDocument:
            if path.name == "bad.pdf":
                raise ExtractorError("tệp hỏng")
            return super().extract(path)

    monkeypatch.setattr(ingest_cli, "build_extractors", lambda s: [Flaky("docling", suffixes=OFFICE, doc=DOC)])
    job = _job(client, _upload(client, "bad.pdf", "good.docx"))
    assert job["status"] == "done"
    by_name = {f["name"]: f for f in job["result"]["files"]}
    assert "tệp hỏng" in by_name["bad.pdf"]["error"] and by_name["good.docx"]["chunks"] == 2
    assert job["result"]["chunks_indexed"] == 2
    assert len(vectors.search("PACK01", k=10)) == 2
