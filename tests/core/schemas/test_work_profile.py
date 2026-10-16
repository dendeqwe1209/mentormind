"""spec 01 AC-04 — WorkProfile Pydantic model and JSON contract agree."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from pydantic import ValidationError

from mentormind.core.schemas import ContractValidationError, WorkProfile, validate_against_contract

APPROVED_PROFILE: dict[str, Any] = {
    "schema_version": "1.0",
    "profile_id": "WP-PACK01-003",
    "process_id": "PACK01",
    "step_order": 3,
    "step": "Đặt linh kiện A vào ngăn trái",
    "hand_action": "tay phải nhặt, xoay 90 độ, đặt nghiêng",
    "objects": ["linh kiện A", "khay chia ngăn"],
    "key_point": "chân linh kiện hướng ra ngoài",
    "reason": "tránh trầy bề mặt khi đóng nắp hộp",
    "reason_source": "expert_verbal",
    "exceptions": [{"case": "thiếu 1 món", "handling": "báo quản lý ca, không tự thay thế"}],
    "pass_criteria": "không có khe hở > 2mm giữa linh kiện và vách ngăn",
    "equipment_id": "SIGMA-EQ-2201",
    "part_numbers": ["A123"],
    "expert": {"expert_id": "EXP-001", "display_name": "Nguyễn Văn A"},
    "evidence": {
        "video_id": "VID-PACK01-0001",
        "t_start": 14.0,
        "t_end": 19.0,
        "segment_ids": ["VID-PACK01-0001#s03"],
        "keyframes": [],
        "transcript_excerpt": "tôi xoay ngược vì nếu không sẽ trầy mặt",
        "document_refs": [],
    },
    "confidence": 0.82,
    "generated_by": "vlm",
    "model_info": {"provider": "local_openai", "model": "Qwen3-VL-8B-Instruct", "fps": 4},
    "data_classification": "synthetic",
    "status": "approved",
    "review": {
        "reviewer": "EXP-001",
        "reviewed_at": "2026-09-25T09:30:00+07:00",
        "comment": None,
        "error_tags": [],
    },
    "created_at": "2026-09-24T15:02:00+07:00",
    "version": 2,
}


def vlm_draft(**overrides: Any) -> dict[str, Any]:
    draft = copy.deepcopy(APPROVED_PROFILE)
    draft.update(status="draft", review=None, reason=None, reason_source=None, version=1)
    draft.update(overrides)
    return draft


def test_ac_04_valid_profile_passes_pydantic_and_contract() -> None:
    validate_against_contract(APPROVED_PROFILE)
    profile = WorkProfile.model_validate(APPROVED_PROFILE)
    validate_against_contract(profile)  # the dump round-trips through the contract too


def test_ac_04_vlm_draft_with_reason_rejected_by_both() -> None:
    bad = vlm_draft(reason="tránh trầy", reason_source="expert_verbal")
    with pytest.raises(ContractValidationError):
        validate_against_contract(bad)
    with pytest.raises(ValidationError, match="reason"):
        WorkProfile.model_validate(bad)


def test_ac_04_vlm_draft_without_reason_is_valid() -> None:
    draft = vlm_draft()
    validate_against_contract(draft)
    validate_against_contract(WorkProfile.model_validate(draft))


def test_contract_rule_reason_needs_expert_source() -> None:
    bad = vlm_draft(status="in_review", reason="tránh trầy", reason_source=None)
    with pytest.raises(ContractValidationError):
        validate_against_contract(bad)
    with pytest.raises(ValidationError):
        WorkProfile.model_validate(bad)


def test_contract_rule_approved_needs_reviewer() -> None:
    bad = copy.deepcopy(APPROVED_PROFILE)
    bad["review"] = {"comment": "ok"}
    with pytest.raises(ContractValidationError):
        validate_against_contract(bad)
    with pytest.raises(ValidationError):
        WorkProfile.model_validate(bad)


def test_optional_non_nullable_fields_are_omitted_not_null() -> None:
    draft = vlm_draft(expert={"expert_id": "EXP-001"}, model_info={"provider": "fake"})
    dumped = WorkProfile.model_validate(draft).to_contract_dict()
    assert dumped["expert"] == {"expert_id": "EXP-001"}
    assert dumped["model_info"] == {"provider": "fake"}
    validate_against_contract(dumped)


def test_unknown_field_rejected_by_both() -> None:
    bad = vlm_draft(surprise=True)
    with pytest.raises(ContractValidationError):
        validate_against_contract(bad)
    with pytest.raises(ValidationError):
        WorkProfile.model_validate(bad)


@pytest.mark.parametrize("actor", ["human", "robot", "machine", None])
def test_ac_18_the_profile_says_who_performs_the_step(actor: str | None) -> None:
    profile = vlm_draft(actor=actor)
    validate_against_contract(profile)
    validate_against_contract(WorkProfile.model_validate(profile))


def test_ac_18_an_actor_outside_the_enum_is_rejected_by_both() -> None:
    bad = vlm_draft(actor="worker")  # worker and engineer are both "human"
    with pytest.raises(ContractValidationError):
        validate_against_contract(bad)
    with pytest.raises(ValidationError):
        WorkProfile.model_validate(bad)
