"""spec 04 §3 — which pass A texts count as English (and get one repair in Vietnamese)."""

from __future__ import annotations

import pytest

from mentormind.processing.vlm.passes.language import english_fields, looks_english
from mentormind.processing.vlm.passes.models import PassAOutput


@pytest.mark.parametrize(
    ("text", "english"),
    [
        ("Pick product", True),
        ("Place product into box", True),
        ("Nhặt sản phẩm từ băng tải", False),
        ("Robot SCARA gắp linh kiện", False),
        ("SCARA", False),  # one token: a name or a code, not judged
        ("", False),
        (None, False),
    ],
)
def test_english_is_two_latin_words_without_a_vietnamese_letter(text: str | None, english: bool) -> None:
    assert looks_english(text) is english


def test_every_english_step_field_is_named() -> None:
    output = PassAOutput.model_validate(
        {
            "scene": "x",
            "steps": [
                {"step": "Đặt hộp", "hand_action": "tay phải ấn", "t_start_rel": 0, "t_end_rel": 1, "confidence": 0.8},
                {
                    "step": "Close lid",
                    "key_point_observed": "both corners first",
                    "t_start_rel": 1,
                    "t_end_rel": 2,
                    "confidence": 0.7,
                },
            ],
        }
    )
    assert english_fields(output) == ["steps[1].step", "steps[1].key_point_observed"]
