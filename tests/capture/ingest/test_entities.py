"""spec 02 FR-05 — process_ids / part_numbers recognition."""

from __future__ import annotations

import pytest

from mentormind.capture.ingest.entities import compile_regex, find_part_numbers, find_process_ids
from mentormind.core.config import Settings

SETTINGS = Settings(_env_file=None)


def test_process_ids_regex_default() -> None:
    text = "Công đoạn PACK01 sau SOLD12, không phải pack01 hay ABCDEF12."
    found = find_process_ids(text, compile_regex(SETTINGS.process_id_regex, "process_id_regex"))
    assert found == ["PACK01", "SOLD12"]


def test_process_ids_deduplicated_in_order_of_appearance() -> None:
    pattern = compile_regex(SETTINGS.process_id_regex, "process_id_regex")
    assert find_process_ids("SOLD12 PACK01 SOLD12", pattern) == ["SOLD12", "PACK01"]


def test_process_ids_stoplist() -> None:
    pattern = compile_regex(SETTINGS.process_id_regex, "process_id_regex")
    assert find_process_ids("ISO27 PACK01 REV01", pattern, stoplist=["ISO27", "REV01"]) == ["PACK01"]


def test_part_numbers_regex() -> None:
    pattern = compile_regex(SETTINGS.part_number_regex, "part_number_regex")
    text = "DENSO PART NUMBER: AA123456-7890; xem thêm BB000001-0002."
    assert find_part_numbers(text, pattern) == ["AA123456-7890", "BB000001-0002"]


def test_invalid_regex_raises() -> None:
    with pytest.raises(ValueError, match="process_id_regex"):
        compile_regex("([A-Z", "process_id_regex")
