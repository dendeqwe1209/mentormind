"""Unit tests for ProfileStore and WorkProfile contract validation.

Acceptance Criteria tested:
- AC-01: PATCH an approved profile -> version += 1, status = in_review
- AC-02: review approve -> status = approved, review info saved
- AC-03: review reject without comment -> error raised
- Constitution Rule 3: VLM draft with reason rejected
"""

import pytest

from mentormind.core.schemas import (
    ProfilePatchRequest,
    ReviewAction,
    ReviewRequest,
    WorkProfile,
)
from mentormind.knowledge_base.store.profile_store import ProfileStore


@pytest.fixture
def temp_store(tmp_path):
    db_file = tmp_path / "test_profiles.sqlite"
    return ProfileStore(db_path=str(db_file))


@pytest.fixture
def valid_profile_data():
    return {
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
            "keyframes": ["kf_01.jpg", "kf_02.jpg", "kf_03.jpg"],
        },
        "confidence": 0.95,
        "generated_by": "vlm",
        "data_classification": "synthetic",
        "status": "draft",
        "created_at": "2026-09-28T10:00:00Z",
        "version": 1,
    }


def test_constitution_vlm_draft_cannot_have_reason(valid_profile_data):
    """Constitution Điều 3: Draft sinh bởi VLM không được có reason."""
    bad_data = dict(valid_profile_data)
    bad_data["reason"] = "Vì chuyên gia bảo thế"
    bad_data["reason_source"] = "expert_verbal"

    with pytest.raises(ValueError, match="Constitution Điều 3"):
        WorkProfile.model_validate(bad_data)


def test_reason_requires_source(valid_profile_data):
    """Có reason thì bắt buộc phải có reason_source."""
    data = dict(valid_profile_data)
    data["status"] = "in_review"
    data["reason"] = "Cần mở dứt khoát để không kẹt băng chuyền"
    data["reason_source"] = None

    with pytest.raises(ValueError, match="Bắt buộc phải chọn reason_source"):
        WorkProfile.model_validate(data)


def test_save_and_get_profile(temp_store, valid_profile_data):
    profile = WorkProfile.model_validate(valid_profile_data)
    temp_store.save_profile(profile)

    fetched = temp_store.get_profile("WP-PACK01-001")
    assert fetched is not None
    assert fetched.profile_id == "WP-PACK01-001"
    assert fetched.status == "draft"
    assert fetched.version == 1


def test_ac_02_review_approve(temp_store, valid_profile_data):
    """AC-02: review approve -> status = approved, lưu review event."""
    profile = WorkProfile.model_validate(valid_profile_data)
    temp_store.save_profile(profile)

    req = ReviewRequest(
        action=ReviewAction.APPROVE,
        reviewer="expert_01",
        comment="Thao tác chuẩn xác",
    )
    approved = temp_store.record_review("WP-PACK01-001", req)

    assert approved.status == "approved"
    assert approved.review is not None
    assert approved.review.reviewer == "expert_01"

    details = temp_store.get_profile_with_reviews("WP-PACK01-001")
    assert details is not None
    assert len(details["reviews"]) == 1
    assert details["reviews"][0]["action"] == "approve"


def test_publication_failure_keeps_profile_unapproved(temp_store, valid_profile_data):
    from mentormind.core.schemas import ReviewRequest

    temp_store.save_profile(WorkProfile.model_validate(valid_profile_data))

    def failed_publish(_profile):
        raise RuntimeError("graph unavailable")

    with pytest.raises(RuntimeError, match="graph unavailable"):
        temp_store.record_review(
            "WP-PACK01-001", ReviewRequest(action="approve", reviewer="EXP-1"), before_save=failed_publish
        )
    assert temp_store.get_profile("WP-PACK01-001").status == "draft"


def test_review_event_failure_rolls_back_sqlite_and_compensates_publication(tmp_path, valid_profile_data):
    class FailingEventStore(ProfileStore):
        @staticmethod
        def _write_review_event(cursor, profile_id, review_req, now_str):
            raise RuntimeError("review event write failed")

    store = FailingEventStore(db_path=tmp_path / "failed_review.sqlite")
    store.save_profile(WorkProfile.model_validate(valid_profile_data))
    actions = []
    with pytest.raises(RuntimeError, match="review event write failed"):
        store.record_review(
            "WP-PACK01-001",
            ReviewRequest(action="approve", reviewer="EXP-1"),
            before_save=lambda profile: actions.append("published"),
            rollback_publish=lambda profile: actions.append("unloaded"),
        )
    assert actions == ["published", "unloaded"]
    profile = store.get_profile("WP-PACK01-001")
    assert profile is not None and profile.status == "draft"
    details = store.get_profile_with_reviews("WP-PACK01-001")
    assert details is not None and details["reviews"] == []


def test_ac_03_review_reject_without_comment(temp_store, valid_profile_data):
    """AC-03: review reject không kèm comment -> raise error."""
    profile = WorkProfile.model_validate(valid_profile_data)
    temp_store.save_profile(profile)

    with pytest.raises(ValueError, match="bắt buộc phải nhập lý do"):
        ReviewRequest(
            action=ReviewAction.REJECT,
            reviewer="expert_01",
            comment="",
        )


def test_ac_01_patch_approved_profile_increments_version(temp_store, valid_profile_data):
    """AC-01: PATCH một profile approved -> version tăng, status về in_review."""
    profile = WorkProfile.model_validate(valid_profile_data)
    temp_store.save_profile(profile)

    # Approve trước
    req = ReviewRequest(action=ReviewAction.APPROVE, reviewer="expert_01")
    temp_store.record_review("WP-PACK01-001", req)
    assert temp_store.get_profile("WP-PACK01-001").status == "approved"

    # Giờ sửa (PATCH)
    patch = ProfilePatchRequest(step="Lấy hộp carton từ kệ số 2")
    patched = temp_store.patch_profile("WP-PACK01-001", patch)

    assert patched.version == 2
    assert patched.status == "in_review"
    assert patched.step == "Lấy hộp carton từ kệ số 2"


def test_job_lifecycle(temp_store):
    """Test job creation, status update and retrieval."""
    job = temp_store.create_job("job-123", "vlm_segmentation")
    assert job.job_id == "job-123"
    assert job.status.value == "queued"

    temp_store.update_job("job-123", "running")
    job = temp_store.get_job("job-123")
    assert job.status.value == "running"

    temp_store.update_job("job-123", "done", result={"profiles_count": 5})
    job = temp_store.get_job("job-123")
    assert job.status.value == "done"
    assert job.result == {"profiles_count": 5}
    assert job.finished_at is not None
