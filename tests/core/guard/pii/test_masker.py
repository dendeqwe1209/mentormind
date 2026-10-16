"""spec 01 AC-09 — PII masking of outbound text (bankassist-mcp cases F/M/V)."""

from __future__ import annotations

import pytest

from mentormind.core.guard import (
    PiiMasker,
    PiiVault,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Khách hẹn gọi lại số vợ 0987654321 sau 17h", "Khách hẹn gọi lại số vợ [PHONE_1] sau 17h"),
        ("Gọi số +84912345678 không nghe máy", "Gọi số [PHONE_1] không nghe máy"),  # F-02
        ("CCCD khách là 001199012345, đã đối chiếu", "CCCD khách là [ID_1], đã đối chiếu"),
        ("Email cá nhân an.nguyen@gmail.com", "Email cá nhân [EMAIL_1]"),  # F-04
        ("Chuyển khoản 500000000 đồng", "Chuyển khoản 500000000 đồng"),  # F-05 amount kept
        ("Hẹn ngày 15082026 tại chi nhánh", "Hẹn ngày 15082026 tại chi nhánh"),  # F-06 date kept
        ("Số thẻ 4012888888881881", "Số thẻ [CARD_1]"),  # F-07 Luhn-valid card
        ("Mã tham chiếu 1234567890123456", "Mã tham chiếu 1234567890123456"),  # F-08 not Luhn
        ("Liên hệ 0912345678 hoặc 0987654321", "Liên hệ [PHONE_1] hoặc [PHONE_2]"),  # F-09
        ("khach hen goi lai so 0912345678", "khach hen goi lai so [PHONE_1]"),  # F-10 no accents
        ("Số CMND 123456789 của khách", "Số CMND [ID_1] của khách"),  # CMND needs a keyword
        ("", ""),  # F-11
    ],
)
def test_ac_09_free_text_is_masked_like_bankassist(text: str, expected: str) -> None:
    assert PiiMasker().mask_text(text) == expected


def test_ac_09_same_value_same_token_across_formats() -> None:
    masker = PiiMasker()
    masked = masker.mask_text("Gọi 091 234 5678, rồi +84912345678, rồi 0912345678")
    assert masked == "Gọi [PHONE_1], rồi [PHONE_1], rồi [PHONE_1]"  # M-02


def test_ac_09_known_names_are_masked_whole_and_case_insensitively() -> None:
    masker = PiiMasker(known={"PERSON": ["Nguyễn Văn An", "Trần Thị Ánh-Nguyệt"]})
    masked = masker.mask_text("Chuyên gia nguyễn văn an chỉ Trần Thị Ánh-Nguyệt cách xếp")
    assert "nguyễn" not in masked.lower() and "Ánh-Nguyệt" not in masked  # M-12
    assert masked.count("[PERSON_") == 2


def test_ac_09_restore_round_trips_and_ignores_foreign_tokens() -> None:
    masker = PiiMasker(known={"PERSON": ["Nguyễn Văn An"]})
    original = "Nguyễn Văn An dặn gọi 0987654321 nếu thiếu linh kiện"
    masked = masker.mask_text(original)
    assert masker.vault.restore(masked) == original  # V-01
    assert masker.vault.restore("[PHONE_9] và [PERSON_1]") == "[PHONE_9] và Nguyễn Văn An"  # V-02


def test_ac_09_vaults_are_isolated_per_session() -> None:
    first, second = PiiMasker(), PiiMasker()
    first.mask_text("0987654321")
    assert second.mask_text("0912345678") == "[PHONE_1]"  # M-04: numbering restarts
    assert second.vault.restore("[PHONE_1]") == "0912345678"  # V-03: no cross-session values


def test_ac_09_site_specific_codes_via_extra_patterns() -> None:
    masker = PiiMasker(extra_patterns={"EQUIPMENT": r"SIGMA-EQ-\d+"})
    assert masker.mask_text("Máy SIGMA-EQ-2201 hỏng") == "Máy [EQUIPMENT_1] hỏng"


def test_ac_09_vault_refuses_to_grow_past_its_limit() -> None:
    vault = PiiVault(max_entries=1)
    vault.tokenize("0987654321", "PHONE")
    with pytest.raises(OverflowError):
        vault.tokenize("0912345678", "PHONE")  # V-05
