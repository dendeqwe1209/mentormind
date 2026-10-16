"""spec 04 §3 — read spec 03's ``transcript.json``; missing or unusable means no transcript."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mentormind.processing.vlm.transcript import load_transcript, transcript_path
from tests.processing.vlm.transcript.fakes import line


def write(tmp_path: Path, rows: object) -> None:
    path = transcript_path(tmp_path, "VID-TEST")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


def test_no_transcript_file_is_no_transcript(tmp_path: Path) -> None:
    assert load_transcript(tmp_path, "VID-TEST") == []


def test_the_lines_spec_03_wrote_are_read_back(tmp_path: Path) -> None:
    other = line("video khác", 3, 4).model_dump(mode="json") | {"video_id": "VID-OTHER"}
    write(tmp_path, [line("Đặt nghiêng", 1, 2).model_dump(mode="json"), other])
    assert [t.text for t in load_transcript(tmp_path, "VID-TEST")] == ["Đặt nghiêng"]


@pytest.mark.parametrize("rows", [{"text": "không phải danh sách"}, [{"text": "thiếu t_start"}]])
def test_an_unusable_file_is_no_transcript_never_a_crash(
    tmp_path: Path, rows: object, caplog: pytest.LogCaptureFixture
) -> None:
    write(tmp_path, rows)
    assert load_transcript(tmp_path, "VID-TEST") == []
    assert "transcript.json" in caplog.text
