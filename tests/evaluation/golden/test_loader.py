"""spec 09 T09-1 — golden set schema and validator (AC-01)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mentormind.evaluation.golden import GoldenSetError, check_distribution, load_golden

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "eval" / "qa_5.jsonl"


def test_the_fixture_loads() -> None:
    questions = load_golden(FIXTURE)
    assert [q.qid for q in questions] == ["Q001", "Q002", "Q003", "Q004", "Q005"]


def test_ac_01_a_line_without_ground_truth_is_reported_by_line_and_nothing_runs(
    tmp_path: Path,
) -> None:
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    broken = json.loads(lines[2])
    del broken["ground_truth"]
    lines[2] = json.dumps(broken, ensure_ascii=False)
    path = tmp_path / "qa.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(GoldenSetError) as caught:
        load_golden(path)
    assert "dòng 3" in str(caught.value) and "ground_truth" in str(caught.value)
    assert caught.value.errors[0].line == 3


def test_bad_json_duplicates_and_unknown_types_are_all_reported(tmp_path: Path) -> None:
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[0]  # duplicate Q001
    lines[3] = lines[3].replace('"relational"', '"trivia"')
    lines.append("{not json")
    path = tmp_path / "qa.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(GoldenSetError) as caught:
        load_golden(path)
    assert [e.line for e in caught.value.errors] == [2, 4, 6]


def test_the_distribution_check_lists_what_is_missing() -> None:
    missing = check_distribution(load_golden(FIXTURE))
    assert "tối thiểu 30 câu" in missing[0]
    assert any(m.startswith("how") for m in missing)
