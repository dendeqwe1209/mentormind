"""spec 01 AC-10 — LeakGuard finds residue (bankassist-mcp cases G-01..G-04)."""

from __future__ import annotations

import pytest

from mentormind.core.guard import (
    LeakGuard,
)


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("đã che hết: [PHONE_1] [ID_1]", None),  # G-01
        ('{"note": "gọi 0987654321"}', "PHONE"),  # G-02
        ('{"note": "CCCD 001199012345"}', "ID"),  # G-03
        ('{"note": "an@example.com"}', "EMAIL"),  # G-04
    ],
)
def test_ac_10_leak_guard_finds_residue(text: str, kind: str | None) -> None:
    assert LeakGuard().check(text) == kind


def test_ac_10_known_values_left_in_text_are_a_leak() -> None:
    guard = LeakGuard(known_values=["Nguyễn Văn An"])
    assert guard.check("hỏi anh nguyễn văn an") == "KNOWN_VALUE"
