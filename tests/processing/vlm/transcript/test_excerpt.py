"""spec 04 §3 / AC-22 — every transcript line goes to exactly one step (window [t_start - lead, t_end + lag])."""

from __future__ import annotations

import pytest

from mentormind.capture.video import align_transcript
from mentormind.processing.vlm.passes.models import TimedStep
from mentormind.processing.vlm.transcript import align, excerpt_text, lines_by_step
from tests.processing.vlm.passes.test_describe import segments
from tests.processing.vlm.transcript.fakes import line, remove_spec03

SAID = [line("rồi đóng nắp.", 12, 14), line("Đặt nghiêng để không trầy,", 3, 5)]


def step(name: str, start: float, end: float, segment: str = "VID-TEST-S001", *more: str) -> TimedStep:
    return TimedStep(
        segment_id=segment, t_start=start, t_end=end, step=name, confidence=0.8, fps=4.0,
        segment_ids=[segment, *more] if more else [],
    )  # fmt: skip


def quoted(steps: list[TimedStep], said: list, **window: float) -> dict[str, str | None]:
    aligned = align_transcript(segments(3), said)  # spec 03's real alignment (FR-08)
    by_step = lines_by_step(steps, aligned, **window)
    return {s.step: excerpt_text(lines) for s, lines in zip(steps, by_step, strict=True)}


def test_ac_22_two_steps_of_one_segment_quote_different_lines() -> None:
    steps = [step("Lấy cốc", 1, 4), step("Đặt cốc vào thùng", 6, 9)]
    said = [line("Cầm cốc ở thân, không cầm miệng.", 1.5, 3), line("Đặt nghiêng để không trầy.", 6.5, 8)]
    assert quoted(steps, said) == {
        "Lấy cốc": "Cầm cốc ở thân, không cầm miệng.",
        "Đặt cốc vào thùng": "Đặt nghiêng để không trầy.",
    }


def test_ac_22_a_comment_right_after_the_action_goes_to_that_action() -> None:
    steps = [step("Ấn nắp", 1, 4), step("Dán nhãn", 8.5, 9.5)]
    after = [line("Ấn đến khi nghe tiếng tách.", 4.5, 6.5)]  # inside the 3 s lag of "Ấn nắp"
    assert quoted(steps, after) == {"Ấn nắp": "Ấn đến khi nghe tiếng tách.", "Dán nhãn": None}
    assert quoted(steps, after, lag_s=0.0) == {"Ấn nắp": "Ấn đến khi nghe tiếng tách.", "Dán nhãn": None}  # nearest


def test_ac_22_a_line_across_two_steps_goes_to_the_step_it_covers_more() -> None:
    steps = [step("Gấp nắp", 0, 5), step("Ấn nắp", 5, 9)]
    across = [line("Gấp xong thì ấn đều hai góc.", 4, 7)]  # 1 s in the first step, 2 s in the second
    assert quoted(steps, across) == {"Gấp nắp": None, "Ấn nắp": "Gấp xong thì ấn đều hai góc."}


def test_ac_22_each_line_is_quoted_once_and_a_merged_step_quotes_both_segments() -> None:
    merged = step("Đặt cốc vào thùng", 8, 13, "VID-TEST-S001", "VID-TEST-S002")
    steps = [step("Lấy cốc", 0, 3), merged, step("Kiểm tra", 22, 25, "VID-TEST-S003")]
    said = [line("Lấy hai cốc một lần.", 0.5, 2), *SAID, line("Đặt nghiêng nhé.", 9, 10)]
    out = quoted(steps, said)
    assert out["Đặt cốc vào thùng"] == "Đặt nghiêng nhé. rồi đóng nắp."
    assert out["Lấy cốc"] == "Lấy hai cốc một lần. Đặt nghiêng để không trầy,"
    assert out["Kiểm tra"] is None
    everything = " ".join(v for v in out.values() if v)
    assert all(everything.count(t.text) == 1 for t in said)  # no line quoted twice


def test_without_spec_03_there_is_no_excerpt_and_no_error(monkeypatch: pytest.MonkeyPatch) -> None:
    remove_spec03(monkeypatch)
    assert align(segments(2), SAID) is None
    assert lines_by_step([step("Lấy cốc", 1, 4)], None) == [[]]


def test_without_a_transcript_there_is_no_excerpt() -> None:
    assert align(segments(2), []) is None
    assert excerpt_text([]) is None
