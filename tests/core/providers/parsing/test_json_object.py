"""Tolerant extraction of the JSON object a model returns."""

from __future__ import annotations

import pytest

from mentormind.core.providers.parsing import parse_json_object


@pytest.mark.parametrize(
    "text",
    [
        '{"steps": []}',
        '```json\n{"steps": []}\n```',
        'Đây là kết quả:\n{"steps": []}\nHết.',
    ],
)
def test_parse_json_object_is_tolerant(text: str) -> None:
    assert parse_json_object(text) == {"steps": []}
