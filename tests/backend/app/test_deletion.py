"""spec 08 §2 "Xoá dữ liệu", AC-19..AC-22 — deleting steps and whole videos.

No Neo4j, no PostgreSQL: the real ``KnowledgeGraphLoader`` runs on a fake graph that only tracks
``Step`` nodes and on an in-memory vector store; the profile store is SQLite in ``tmp_path``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from mentormind.backend.app.deps import get_knowledge_loader, get_loader_opener, get_profile_store
from mentormind.backend.app.main import app
from mentormind.backend.app.routers import videos as videos_router
from mentormind.backend.app.video_jobs import running_videos
from mentormind.core.config import Settings
from mentormind.core.schemas import Evidence, Review, VideoAsset, VideoProcessResult, WorkProfile
from mentormind.knowledge_base.kg.loader import KnowledgeGraphLoader
from mentormind.knowledge_base.store.profile_store import ProfileStore
from mentormind.knowledge_base.store.vector_store import MemoryVectorStore

VIDEO_A, VIDEO_B = "VID-aaaaaaaaaaaa", "VID-bbbbbbbbbbbb"
APPROVE = {"action": "approve", "reviewer": "expert_01"}


class StepGraph:
    """The ``Step`` nodes a Neo4j would hold after the loader's queries."""

    def __init__(self) -> None:
        self.steps: set[str] = set()

    def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        if "MERGE (s:Step" in query:
            self.steps.add(params["profile_id"])
        if "DETACH DELETE s" in query:
            self.steps.discard(params["profile_id"])
        return []


class FakeKnowledge:
    """Neo4j + pgvector behind ``get_loader_opener``; ``down`` makes opening them fail."""

    def __init__(self) -> None:
        self.graph = StepGraph()
        self.vectors = MemoryVectorStore()
        self.down = False
        self.opened = 0

    def loader(self) -> KnowledgeGraphLoader:
        return KnowledgeGraphLoader(self.graph, self.vectors)

    @contextmanager
    def open(self) -> Iterator[KnowledgeGraphLoader]:
        self.opened += 1
        if self.down:
            raise RuntimeError("Neo4j không phản hồi")
        yield self.loader()

    def chunk_of(self, profile_id: str) -> bool:
        return bool(self.vectors.search("", k=1, filters={"source_type": "work_profile", "ref_id": profile_id}))


def step(number: int, video_id: str = VIDEO_A) -> WorkProfile:
    return WorkProfile(
        schema_version="1.0",
        profile_id=f"WP-PACK01-{number:03d}",
        process_id="PACK01",
        step_order=number,
        step=f"Lấy linh kiện bước {number}",
        hand_action="Cầm linh kiện",
        evidence=Evidence(video_id=video_id, t_start=number, t_end=number + 1),
        confidence=0.9,
        generated_by="vlm",
        data_classification="synthetic",
        status="draft",
        created_at="2026-10-08T00:00:00Z",
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, work_dir=tmp_path / "work")


@pytest.fixture
def store(tmp_path: Path) -> ProfileStore:
    store = ProfileStore(db_path=tmp_path / "profiles.sqlite")
    for number in (1, 2, 3):
        store.save_profile(step(number))
    store.save_profile(step(4, VIDEO_B))
    return store


@pytest.fixture
def kg() -> FakeKnowledge:
    return FakeKnowledge()


@pytest.fixture
def client(
    store: ProfileStore, kg: FakeKnowledge, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setattr(videos_router, "get_settings", lambda: settings)
    app.dependency_overrides[get_profile_store] = lambda: store
    app.dependency_overrides[get_knowledge_loader] = kg.loader
    app.dependency_overrides[get_loader_opener] = lambda: kg.open
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _approve(client: TestClient, kg: FakeKnowledge, profile_id: str) -> None:
    assert client.post(f"/profiles/{profile_id}/review", json=APPROVE).status_code == 200
    assert profile_id in kg.graph.steps and kg.chunk_of(profile_id)


def _ids(client: TestClient) -> set[str]:
    return {p["profile_id"] for p in client.get("/profiles").json()}


def test_ac_19_deleting_a_draft_never_opens_the_graph(
    client: TestClient, store: ProfileStore, kg: FakeKnowledge
) -> None:
    kg.down = True  # Neo4j and pgvector are off: a draft is still deleted
    res = client.delete("/profiles/WP-PACK01-001")
    assert res.status_code == 200, res.text
    assert res.json() == {"deleted": ["WP-PACK01-001"], "unpublished": [], "failed": []}
    assert client.get("/profiles/WP-PACK01-001").status_code == 404
    assert "WP-PACK01-001" not in _ids(client) and kg.opened == 0


def test_ac_19_a_rejected_step_goes_with_its_review_history(
    client: TestClient, store: ProfileStore, kg: FakeKnowledge
) -> None:
    reject = {"action": "reject", "reviewer": "expert_01", "comment": "bịa bước"}
    assert client.post("/profiles/WP-PACK01-002/review", json=reject).status_code == 200
    kg.opened = 0
    assert client.delete("/profiles/WP-PACK01-002").status_code == 200
    assert store.get_profile("WP-PACK01-002") is None and store.last_review_action("WP-PACK01-002") is None
    assert kg.opened == 0


def test_ac_19_unknown_step_is_404(client: TestClient) -> None:
    res = client.delete("/profiles/WP-PACK01-999")
    assert res.status_code == 404 and "WP-PACK01-999" in res.json()["detail"]


def test_ac_20_an_approved_step_leaves_the_graph_and_the_vector_store(client: TestClient, kg: FakeKnowledge) -> None:
    _approve(client, kg, "WP-PACK01-001")
    res = client.delete("/profiles/WP-PACK01-001")
    assert res.status_code == 200, res.text
    assert res.json()["unpublished"] == ["WP-PACK01-001"] and res.json()["deleted"] == ["WP-PACK01-001"]
    assert kg.graph.steps == set() and not kg.chunk_of("WP-PACK01-001")
    assert client.get("/profiles/WP-PACK01-001").status_code == 404


def test_ac_20_an_edited_approved_step_is_still_in_the_graph_and_leaves_it(
    client: TestClient, kg: FakeKnowledge
) -> None:
    _approve(client, kg, "WP-PACK01-001")
    edited = client.patch("/profiles/WP-PACK01-001", json={"step": "Lấy linh kiện từ khay"}).json()
    assert edited["status"] == "in_review" and "WP-PACK01-001" in kg.graph.steps  # AC-01
    assert client.delete("/profiles/WP-PACK01-001").json()["unpublished"] == ["WP-PACK01-001"]
    assert kg.graph.steps == set() and not kg.chunk_of("WP-PACK01-001")


def test_ac_20_graph_down_keeps_the_approved_step_and_says_why(
    client: TestClient, store: ProfileStore, kg: FakeKnowledge
) -> None:
    _approve(client, kg, "WP-PACK01-001")
    kg.down = True
    res = client.delete("/profiles/WP-PACK01-001")
    assert res.status_code == 503
    assert "Neo4j không phản hồi" in res.json()["detail"] and "giữ nguyên" in res.json()["detail"]
    kept = store.get_profile("WP-PACK01-001")
    assert kept is not None and kept.status == "approved"
    assert kg.graph.steps == {"WP-PACK01-001"} and kg.chunk_of("WP-PACK01-001")


def test_ac_21_several_steps_are_deleted_together(client: TestClient, kg: FakeKnowledge) -> None:
    _approve(client, kg, "WP-PACK01-002")
    ids = ["WP-PACK01-001", "WP-PACK01-002", "WP-PACK01-003", "WP-PACK01-001"]  # a repeat counts once
    res = client.post("/profiles/delete", json={"profile_ids": ids})
    assert res.status_code == 200, res.text
    assert res.json() == {
        "deleted": ["WP-PACK01-001", "WP-PACK01-002", "WP-PACK01-003"],
        "unpublished": ["WP-PACK01-002"],
        "failed": [],
    }
    assert _ids(client) == {"WP-PACK01-004"} and kg.graph.steps == set()


def test_ac_21_an_unknown_id_deletes_nothing(client: TestClient) -> None:
    res = client.post("/profiles/delete", json={"profile_ids": ["WP-PACK01-001", "WP-NOPE-001"]})
    assert res.status_code == 404 and "WP-NOPE-001" in res.json()["detail"]
    assert "WP-PACK01-001" in _ids(client)
    assert client.post("/profiles/delete", json={"profile_ids": []}).status_code == 422


def test_ac_21_graph_down_still_deletes_drafts_and_reports_the_rest(
    client: TestClient, store: ProfileStore, kg: FakeKnowledge
) -> None:
    _approve(client, kg, "WP-PACK01-002")
    kg.down = True
    res = client.post("/profiles/delete", json={"profile_ids": ["WP-PACK01-001", "WP-PACK01-002"]})
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["deleted"], body["unpublished"]) == (["WP-PACK01-001"], [])
    [failure] = body["failed"]
    assert failure["profile_id"] == "WP-PACK01-002" and "Neo4j không phản hồi" in failure["error"]
    assert store.get_profile("WP-PACK01-001") is None and store.get_profile("WP-PACK01-002") is not None


def _video_files(settings: Settings, video_id: str) -> list[Path]:
    folder = settings.work_dir / "video" / video_id
    files = [
        folder / "source.mp4",
        folder / "video.json",
        folder / "segments.json",
        folder / "transcript.json",
        folder / "keyframes" / f"{video_id}-S001_k1.jpg",
        folder / "clips" / f"{video_id}-S001.mp4",
        settings.work_dir / "vlm" / video_id / "describe-fake" / "pass_a.json",
    ]
    for path in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    return files


def test_ac_22_a_video_goes_with_its_steps_and_files(client: TestClient, settings: Settings, kg: FakeKnowledge) -> None:
    files_a, files_b = _video_files(settings, VIDEO_A), _video_files(settings, VIDEO_B)
    _approve(client, kg, "WP-PACK01-002")
    res = client.delete(f"/videos/{VIDEO_A}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["video_id"] == VIDEO_A and body["files_removed"] == len(files_a)
    assert sorted(body["deleted"]) == ["WP-PACK01-001", "WP-PACK01-002", "WP-PACK01-003"]
    assert (body["unpublished"], body["failed"]) == (["WP-PACK01-002"], [])
    assert not (settings.work_dir / "video" / VIDEO_A).exists() and not (settings.work_dir / "vlm" / VIDEO_A).exists()
    assert kg.graph.steps == set()
    assert _ids(client) == {"WP-PACK01-004"} and all(f.exists() for f in files_b)  # the other video stays


def test_ac_22_unknown_video_is_404(client: TestClient, settings: Settings) -> None:
    assert client.delete("/videos/VID-cccccccccccc").status_code == 404
    assert client.delete("/videos/a.b").status_code == 404  # not a plain folder name
    _video_files(settings, "VID-dddddddddddd")  # files without steps can still be deleted
    assert client.delete("/videos/VID-dddddddddddd").json()["files_removed"] == 7


def test_ac_22_files_stay_while_an_approved_step_cannot_be_unloaded(
    client: TestClient, settings: Settings, store: ProfileStore, kg: FakeKnowledge
) -> None:
    files = _video_files(settings, VIDEO_A)
    _approve(client, kg, "WP-PACK01-002")
    kg.down = True
    res = client.delete(f"/videos/{VIDEO_A}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert sorted(body["deleted"]) == ["WP-PACK01-001", "WP-PACK01-003"] and body["files_removed"] == 0
    assert [f["profile_id"] for f in body["failed"]] == ["WP-PACK01-002"]
    assert all(f.exists() for f in files) and store.get_profile("WP-PACK01-002") is not None


def test_ac_20_a_step_that_came_in_approved_then_edited_still_leaves_the_graph(
    client: TestClient, store: ProfileStore, kg: FakeKnowledge
) -> None:
    # As seed_demo / an imported profile: approved with a review block but no review event,
    # published by `knowhow kg load-profiles`.
    review = Review(reviewer="Kỹ sư QA", reviewed_at="2026-09-28T08:00:00Z")
    store.save_profile(step(1).model_copy(update={"status": "approved", "review": review}))
    kg.loader().load_profiles(store.list_profiles())
    assert kg.graph.steps == {"WP-PACK01-001"} and store.last_review_action("WP-PACK01-001") is None
    assert (
        client.patch("/profiles/WP-PACK01-001", json={"step": "Lấy linh kiện từ khay"}).json()["status"] == "in_review"
    )
    res = client.delete("/profiles/WP-PACK01-001")
    assert res.status_code == 200, res.text
    assert res.json()["unpublished"] == ["WP-PACK01-001"]
    assert kg.graph.steps == set() and not kg.chunk_of("WP-PACK01-001")


def test_ac_20_the_list_says_which_steps_the_graph_serves(client: TestClient, kg: FakeKnowledge) -> None:
    _approve(client, kg, "WP-PACK01-001")
    _approve(client, kg, "WP-PACK01-002")
    assert client.patch("/profiles/WP-PACK01-001", json={"step": "Lấy linh kiện từ khay"}).status_code == 200
    reject = {"action": "reject", "reviewer": "expert_01", "comment": "sai thao tác"}
    assert client.post("/profiles/WP-PACK01-003/review", json=reject).status_code == 200
    listed = {p["profile_id"]: (p["status"], p["published"]) for p in client.get("/profiles").json()}
    assert listed == {
        "WP-PACK01-001": ("in_review", True),  # edited after approval: the graph keeps the old version
        "WP-PACK01-002": ("approved", True),
        "WP-PACK01-003": ("rejected", False),
        "WP-PACK01-004": ("draft", False),
    }


def test_ac_20_a_locked_store_deletes_nothing_and_keeps_the_graph(
    client: TestClient, store: ProfileStore, kg: FakeKnowledge
) -> None:
    _approve(client, kg, "WP-PACK01-001")
    store.timeout_s = 0.1
    other = sqlite3.connect(store.db_path)
    other.execute("BEGIN IMMEDIATE")  # another write (an approve publishing) holds the lock
    try:
        res = client.delete("/profiles/WP-PACK01-001")
        assert res.status_code == 503 and "đang bận" in res.json()["detail"]
        assert kg.graph.steps == {"WP-PACK01-001"} and kg.chunk_of("WP-PACK01-001")  # never unloaded
    finally:
        other.rollback()
        other.close()
    kept = store.get_profile("WP-PACK01-001")
    assert kept is not None and kept.status == "approved"
    assert client.delete("/profiles/WP-PACK01-001").json()["unpublished"] == ["WP-PACK01-001"]


def test_ac_22_a_video_whose_job_is_running_cannot_be_deleted(
    client: TestClient, settings: Settings, store: ProfileStore, kg: FakeKnowledge
) -> None:
    files = _video_files(settings, VIDEO_A)
    running_videos.hold(VIDEO_A)
    try:
        res = client.delete(f"/videos/{VIDEO_A}")
        assert res.status_code == 409 and "đang được xử lý" in res.json()["detail"]
        assert client.delete("/profiles/WP-PACK01-001").status_code == 409
        many = client.post("/profiles/delete", json={"profile_ids": ["WP-PACK01-004", "WP-PACK01-002"]})
        assert many.status_code == 409 and VIDEO_A in many.json()["detail"]
        assert _ids(client) == {"WP-PACK01-001", "WP-PACK01-002", "WP-PACK01-003", "WP-PACK01-004"}
        assert all(f.exists() for f in files)
        assert client.delete("/profiles/WP-PACK01-004").status_code == 200  # another video's step
    finally:
        running_videos.release(VIDEO_A)
    assert client.delete(f"/videos/{VIDEO_A}").status_code == 200


@pytest.mark.parametrize("fails", [False, True])
def test_ac_22_the_process_job_holds_its_video_until_it_ends(
    fails: bool, client: TestClient, settings: Settings, store: ProfileStore, kg: FakeKnowledge,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    folder = settings.work_dir / "video" / VIDEO_A
    folder.mkdir(parents=True)
    asset = VideoAsset(
        video_id=VIDEO_A, path=str(folder / "source.mp4"), duration_s=10.0, fps=25.0, has_audio=False,
        process_id="PACK01", data_classification="synthetic",
    )  # fmt: skip
    (folder / "video.json").write_text(asset.model_dump_json(), encoding="utf-8")
    refused: list[int] = []

    def describe(asset: VideoAsset, **kwargs: Any) -> VideoProcessResult:
        try:  # the user deletes the video while the job still saves steps
            videos_router.delete_video(VIDEO_A, store=store, open_loader=kg.open)
        except HTTPException as exc:
            refused.append(exc.status_code)
        if fails:
            raise RuntimeError("VLM lỗi")
        return VideoProcessResult(video_id=VIDEO_A, process_id="PACK01")

    monkeypatch.setattr(videos_router, "describe_video", describe)
    job = client.post(f"/videos/{VIDEO_A}/process", json={"method": "fixed_window"}).json()["job_id"]
    assert refused == [409]
    assert client.get(f"/jobs/{job}").json()["status"] == ("failed" if fails else "done")
    assert "WP-PACK01-001" in _ids(client) and not running_videos.holds(VIDEO_A)
    assert client.delete(f"/videos/{VIDEO_A}").status_code == 200  # once the job ended


def test_ac_22_server_folders_are_not_videos(client: TestClient, settings: Settings) -> None:
    incoming = settings.work_dir / "video" / "_incoming"
    incoming.mkdir(parents=True)
    (incoming / "0123abcd.mp4").write_bytes(b"x")  # an upload in progress
    assert client.delete("/videos/_incoming").status_code == 404
    assert (incoming / "0123abcd.mp4").exists()
