"""spec 04 T04-4 — pass B: keep only the steps both pass-A runs report (AC-04)."""

from __future__ import annotations

from mentormind.core.schemas import Actor
from mentormind.processing.vlm.passes import FailedSegment, PassAResult, TimedStep
from mentormind.processing.vlm.passes.consistency import self_consistent


def timed(
    name: str,
    start: float,
    end: float,
    confidence: float = 0.8,
    seg: str = "S1",
    actor: Actor | None = None,
) -> TimedStep:
    return TimedStep(
        segment_id=seg, t_start=start, t_end=end, step=name, confidence=confidence, fps=4.0,
        actor=actor,
    )  # fmt: skip


def run(*steps: TimedStep, failed: tuple[str, ...] = (), tokens: int = 100) -> PassAResult:
    return PassAResult(
        steps=list(steps),
        failed=[FailedSegment(segment_id=s, error="x", raw_text="") for s in failed],
        prompt_tokens=tokens,
        completion_tokens=10,
        calls=len(steps) or 1,
    )


def test_ac_04_a_step_seen_in_only_one_run_is_dropped() -> None:
    first = run(timed("Nhặt cốc từ khay", 0, 2), timed("Đặt cốc vào thùng", 2, 5))
    second = run(timed("Nhặt cốc từ khay", 0.5, 2.5), timed("Kiểm tra nhãn", 6, 8))
    kept = self_consistent(first, second)
    assert [s.step for s in kept.steps] == ["Nhặt cốc từ khay"]


def test_ac_04_same_words_at_another_time_do_not_confirm_a_step() -> None:
    first = run(timed("Đặt cốc vào thùng", 0, 2))
    second = run(timed("Đặt cốc vào thùng", 5, 7))
    assert self_consistent(first, second).steps == []


def test_steps_are_only_paired_inside_the_same_segment() -> None:
    first = run(timed("Đặt cốc vào thùng", 9, 10, seg="S1"))
    second = run(timed("Đặt cốc vào thùng", 9, 10, seg="S2"))
    assert self_consistent(first, second).steps == []


def test_confidence_is_the_mean_of_both_runs_times_the_match_ratio() -> None:
    first = run(timed("Đặt cốc vào thùng", 0, 2, confidence=0.8))
    second = run(timed("Đặt cốc vào thùng", 0, 2, confidence=0.6))
    [step] = self_consistent(first, second).steps
    assert step.confidence == 0.7  # (0.8 + 0.6) / 2 x 100/100


def test_a_segment_failed_in_either_run_is_failed_and_costs_add_up() -> None:
    first = run(timed("Nhặt cốc", 0, 2, seg="S2"), failed=("S1",), tokens=100)
    second = run(timed("Nhặt cốc", 0, 2, seg="S2"), failed=("S2",), tokens=50)
    result = self_consistent(first, second)
    assert result.steps == []  # S2 could not be confirmed by the second run
    assert sorted(f.segment_id for f in result.failed) == ["S1", "S2"]
    assert result.prompt_tokens == 150 and result.calls == 2


def test_ac_19_runs_that_disagree_on_the_actor_leave_it_unknown() -> None:
    first = run(timed("Đặt cốc vào thùng", 0, 2, actor="robot"))
    second = run(timed("Đặt cốc vào thùng", 0, 2, actor="human"))
    [step] = self_consistent(first, second).steps
    assert step.actor is None


def test_an_actor_only_one_run_could_tell_is_kept() -> None:
    first = run(timed("Đặt cốc vào thùng", 0, 2, actor=None))
    second = run(timed("Đặt cốc vào thùng", 0, 2, actor="machine"))
    [step] = self_consistent(first, second).steps
    assert step.actor == "machine"


def test_ac_24_steps_sharing_a_tiled_span_keep_the_model_order_after_pass_b() -> None:
    # SegmentTiling gives every step with the same start (or clamped to the segment end) one span.
    names = ["Nhặt cốc lên từ bàn", "Đặt cốc vào thùng carton", "Dán băng keo nắp thùng"]
    first = run(*(timed(name, 0, 10) for name in names))
    assert [s.step for s in self_consistent(first, first).steps] == names
    # The later step matching better must not jump ahead either.
    second = run(timed("Nhặt chiếc cốc trên bàn lên", 0, 10), timed("Đặt cốc vào thùng carton", 0, 10))
    kept = self_consistent(run(*(timed(name, 0, 10) for name in names[:2])), second)
    assert [s.step for s in kept.steps] == names[:2]
