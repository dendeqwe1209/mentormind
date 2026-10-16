"""Recognise process ids and part numbers in chunk text (spec 02 FR-05)."""

from __future__ import annotations

import re
from collections.abc import Iterable


def compile_regex(pattern: str, name: str) -> re.Pattern[str]:
    """Compile a configured regex; ``name`` is the setting, so the error says what to fix."""
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"{name} không phải regex hợp lệ ({pattern!r}): {exc}") from exc


def _unique(matches: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(matches))


def find_process_ids(text: str, pattern: re.Pattern[str], stoplist: Iterable[str] = ()) -> list[str]:
    """Distinct matches in order of appearance, minus ``stoplist`` (e.g. ISO27, REV01)."""
    banned = set(stoplist)
    return [m for m in _unique(x.group(0) for x in pattern.finditer(text)) if m not in banned]


def find_part_numbers(text: str, pattern: re.Pattern[str]) -> list[str]:
    return _unique(x.group(0) for x in pattern.finditer(text))
