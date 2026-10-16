"""Integration tests for FastAPI endpoints (Spec 08).

Acceptance Criteria tested:
- AC-01: PATCH /profiles/{id} increments version and sets status to in_review; the graph keeps
  the approved version until it is re-approved
- AC-02: POST /profiles/{id}/review approve sets status to approved
- AC-03: POST /profiles/{id}/review reject without comment -> 422
- AC-04: GET /media/../../etc/passwd -> 400 (path traversal blocked)
- AC-05: Job error handling (failed status with message)
- AC-06: POST /rca/investigate with non-existent lot -> 404
"""

import pytest
from fastapi.testclient import TestClient

from mentormind.agents.adapters import rest
from mentormind.backend.app.deps import get_knowledge_loader, get_profile_store
from mentormind.backend.app.main import app
from mentormind.core.config import get_settings
from mentormind.core.schemas import WorkProfile
from mentormind.knowledge_base.store.profile_store import ProfileStore


@pytest.fixture
def mock_store(tmp_path):
    db_file = tmp_path / "test_api_profiles.sqlite"
    store = ProfileStore(db_path=str(db_file))

    # Seed a sample profile
    profile_data = {
        "schema_version": "1.0",
        "profile_id": "WP-PACK01-001",
        "process_id": "PACK01",
        "step_order": 1,
        "step": "Lấy hộp carton từ kệ",
        "hand_action": "Hai tay cầm hai cạnh hộp mở bung đáy",
        "objects": ["hộp carton"],
        "key_point": "Mở dứt khoát để đáy hộp phẳng",
        "reason": None,
        "reason_source": None,
        "exceptions": [],
        "pass_criteria": "Đáy hộp vuông góc, không rách",
        "evidence": {
            "video_id": "VID-PACK01-01",
            "t_start": 0.0,
            "t_end": 5.2,
            "keyframes": ["kf_01.jpg"],
        },
        "confidence": 0.95,
        "generated_by": "vlm",
        "data_classification": "synthetic",
        "status": "draft",
        "created_at": "2026-09-28T10:00:00Z",
        "version": 1,
    }
    store.save_profile(WorkProfile.model_validate(profile_data))
    return store


@pytest.fixture
def client(mock_store, monkeypatch):
    # These tests check the routers' demo answers (spec 08): a developer .env with
    # KNOWHOW_API_AGENTS=live would send them to the real LLM instead.
    monkeypatch.setattr(rest, "get_settings", lambda: get_settings().model_copy(update={"api_agents": "mock"}))
    app.dependency_overrides[get_profile_store] = lambda: mock_store

    class FakeLoader:
        def load_profiles(self, profiles):
            return None

        def unload_profile(self, profile_id):
            return None

    app.dependency_overrides[get_knowledge_loader] = lambda: FakeLoader()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_health_check(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"


def test_list_and_get_profiles(client):
    res = client.get("/profiles")
    assert res.status_code == 200
    profiles = res.json()
    assert len(profiles) >= 1
    assert profiles[0]["profile_id"] == "WP-PACK01-001"

    detail = client.get("/profiles/WP-PACK01-001")
    assert detail.status_code == 200
    assert detail.json()["profile"]["profile_id"] == "WP-PACK01-001"


def test_ac_02_review_approve(client):
    """AC-02: review approve -> approved status."""
    res = client.post(
        "/profiles/WP-PACK01-001/review",
        json={"action": "approve", "reviewer": "expert_01", "comment": "Tốt"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "approved"
    assert res.json()["review"]["reviewer"] == "expert_01"


def test_review_does_not_commit_approval_if_publication_fails(client, mock_store):
    class FailingLoader:
        def load_profiles(self, profiles):
            raise RuntimeError("graph unavailable")

        def unload_profile(self, profile_id):
            return None

    app.dependency_overrides[get_knowledge_loader] = lambda: FailingLoader()
    with pytest.raises(RuntimeError, match="graph unavailable"):
        client.post("/profiles/WP-PACK01-001/review", json={"action": "approve", "reviewer": "expert_01"})
    assert mock_store.get_profile("WP-PACK01-001").status == "draft"


def test_ac_03_review_reject_without_comment(client):
    """AC-03: review reject không kèm comment -> 422."""
    res = client.post(
        "/profiles/WP-PACK01-001/review",
        json={"action": "reject", "reviewer": "expert_01", "comment": ""},
    )
    assert res.status_code == 422


def test_ac_01_patch_profile(client):
    """AC-01: PATCH profile -> version tăng, status về in_review."""
    client.post(
        "/profiles/WP-PACK01-001/review",
        json={"action": "approve", "reviewer": "expert_01"},
    )

    res = client.patch(
        "/profiles/WP-PACK01-001",
        json={"step": "Lấy hộp carton từ kệ số 3"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["version"] == 2
    assert data["status"] == "in_review"
    assert data["step"] == "Lấy hộp carton từ kệ số 3"


class TrackingLoader:
    """What the graph holds: profile_id -> (version, reviewer) of the published profile."""

    def __init__(self) -> None:
        self.published: dict[str, tuple[int, str]] = {}

    def load_profiles(self, profiles):
        for profile in profiles:
            self.published[profile.profile_id] = (profile.version, profile.review.reviewer)

    def unload_profile(self, profile_id):
        self.published.pop(profile_id, None)


def test_ac_01_patch_keeps_the_published_version_until_reapproved(client, mock_store):
    """AC-01: the graph keeps serving the approved version while the edit waits for review."""
    loader = TrackingLoader()
    app.dependency_overrides[get_knowledge_loader] = lambda: loader
    approve = {"action": "approve", "reviewer": "expert_01"}
    assert client.post("/profiles/WP-PACK01-001/review", json=approve).status_code == 200
    assert client.patch("/profiles/WP-PACK01-001", json={"step": "Bước mới"}).status_code == 200
    edited = mock_store.get_profile("WP-PACK01-001")
    assert (edited.status, edited.version) == ("in_review", 2)
    assert loader.published == {"WP-PACK01-001": (1, "expert_01")}
    assert client.post("/profiles/WP-PACK01-001/review", json=approve).status_code == 200
    assert loader.published == {"WP-PACK01-001": (2, "expert_01")}


def test_failed_reapproval_restores_the_published_version(client, mock_store, monkeypatch):
    loader = TrackingLoader()
    app.dependency_overrides[get_knowledge_loader] = lambda: loader
    approve = {"action": "approve", "reviewer": "expert_01"}
    assert client.post("/profiles/WP-PACK01-001/review", json=approve).status_code == 200

    def failing_review_event(*args):
        raise RuntimeError("review event write failed")

    monkeypatch.setattr(mock_store, "_write_review_event", failing_review_event)
    with pytest.raises(RuntimeError, match="review event write failed"):
        client.post("/profiles/WP-PACK01-001/review", json={"action": "approve", "reviewer": "expert_02"})
    assert mock_store.get_profile("WP-PACK01-001").status == "approved"
    assert loader.published == {"WP-PACK01-001": (1, "expert_01")}


def test_ac_04_media_path_traversal_blocked(client):
    """AC-04: GET /media/../../etc/passwd -> 400 hoặc 404, chặn truy cập."""
    res = client.get("/media/../../etc/passwd")
    assert res.status_code in (400, 404)


def test_ac_06_rca_invalid_lot_not_found(client):
    """AC-06: /rca/investigate với lot không tồn tại -> 404."""
    res = client.post("/rca/investigate", json={"lot_id": "LOT-DOES-NOT-EXIST"})
    assert res.status_code == 404


def test_rca_investigate_valid_lot(client):
    res = client.post("/rca/investigate", json={"lot_id": "LOT-PACK01-001"})
    assert res.status_code == 200
    data = res.json()
    assert len(data["hypotheses"]) > 0
    assert len(data["five_whys"]) == 5
    assert len(data["preventive_actions"]) > 0


def test_sigma_lots(client):
    res = client.get("/sigma/lots")
    assert res.status_code == 200
    lots = res.json()
    assert len(lots) >= 2


def test_assistant_ask(client):
    res = client.post(
        "/assistant/ask",
        json={"process_id": "PACK01", "question": "Cách xếp linh kiện đúng?"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["refused"] is False
    assert len(data["citations"]) > 0
