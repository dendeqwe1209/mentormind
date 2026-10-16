"""spec 04 FR-03/FR-04/FR-06 — DescribePipeline runs passes A, B, C and post-processing."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from mentormind.core.providers.llm.backends.fake import FakeLLM
from mentormind.core.providers.vlm.backends.fake import FakeVLM
from mentormind.core.schemas.video import Segment
from mentormind.core.schemas.work_profile import validate_against_contract
from mentormind.processing.vlm.passes import ObservedStep
from mentormind.processing.vlm.passes.step_times import ModelSpans, PlacedStep
from mentormind.processing.vlm.pipeline import DescribePipeline, read_profiles
from tests.processing.vlm.passes.test_describe import fake_sampler, segments, step


def run(vlm: FakeVLM, tmp_path: Path, llm: FakeLLM | None = None, transcript: Any = (), **kwargs: Any) -> Any:
    pipeline = DescribePipeline(
        vlm, llm=llm, process_id="PACK01", default_fps=4.0, max_frames=48, sampler=fake_sampler,
        **kwargs,
    )  # fmt: skip
    return pipeline.run(segments(2), tmp_path / "run", transcript)


# Segment 1 then 2 for the first pass-A run, the same two again for the second run.
RUN_1 = [
    {"steps": [step("Nhặt cốc từ khay", 0, 2), step("Đặt cốc vào thùng carton", 8, 10)]},
    {"steps": [step("Đặt cốc vào thùng", 0, 1.5), step("Kiểm tra nhãn", 5, 6)]},
]
RUN_2 = [
    {"steps": [step("Nhặt cốc từ khay", 0, 2.5), step("Đặt cốc vào thùng carton", 8.5, 10)]},
    {"steps": [step("Đặt cốc vào thùng", 0, 1.5)]},  # "Kiểm tra nhãn" was a one-off
]


def test_passes_a_b_c_end_in_valid_drafts(tmp_path: Path) -> None:
    llm = FakeLLM(
        [
            {
                "steps": [
                    {"step": "Nhặt cốc từ khay", "source_ids": ["s1"]},
                    {"step": "Đặt cốc vào thùng carton", "source_ids": ["s2", "s3"]},
                ]
            }
        ]
    )
    result = run(FakeVLM([*RUN_1, *RUN_2]), tmp_path, llm=llm)
    assert result.pass_a_steps == 4
    assert [p.step for p in result.profiles] == ["Nhặt cốc từ khay", "Đặt cốc vào thùng carton"]
    merged = result.profiles[1]
    assert merged.evidence.segment_ids == ["VID-TEST-S001", "VID-TEST-S002"]
    # Pass A tiles each segment (AC-24): 8-10 s in S001, then 10-15 s until "Kiểm tra nhãn" in S002.
    assert (merged.evidence.t_start, merged.evidence.t_end) == (8.0, 15.0)
    for profile in result.profiles:
        validate_against_contract(profile)
        assert profile.status == "draft" and profile.reason is None
    work = tmp_path / "run"
    for artefact in ("pass_a", "pass_b/pass_a", "pass_c.json", "predictions.json"):
        assert (work / artefact).exists(), artefact  # FR-06: every pass kept for debugging
    assert [p.step for p in read_profiles(work / "profiles.json")] == [p.step for p in result.profiles]


class RecordingSpans(ModelSpans):
    """``KNOWHOW_VLM_STEP_TIMES=model``, noting each segment it places."""

    def __init__(self) -> None:
        self.placed: list[str] = []

    def place(self, steps: Sequence[ObservedStep], segment: Segment) -> list[PlacedStep]:
        self.placed.append(segment.segment_id)
        return super().place(steps, segment)


def test_ac_28_both_pass_a_runs_keep_the_model_spans_when_asked(tmp_path: Path) -> None:
    llm = FakeLLM([{"steps": [{"step": "Đặt cốc vào thùng carton", "source_ids": ["s2", "s3"]}]}])
    timer = RecordingSpans()
    result = run(FakeVLM([*RUN_1, *RUN_2]), tmp_path, llm=llm, step_timer=timer)
    assert timer.placed == ["VID-TEST-S001", "VID-TEST-S002"] * 2  # passes A and B
    # The model's spans, as before spec 04 v1.22: 0-2 s; 8-10 s in S001 merged with 10-11.5 s in S002.
    spans = {p.step: (p.evidence.t_start, p.evidence.t_end) for p in result.profiles}
    assert spans == {"Nhặt cốc từ khay": (0.0, 2.0), "Đặt cốc vào thùng carton": (8.0, 11.5)}


def test_without_b_and_c_it_is_pass_a_alone(tmp_path: Path) -> None:
    vlm = FakeVLM(RUN_1)
    result = run(vlm, tmp_path, consistency=False)
    assert len(result.profiles) == 4 and len(vlm.calls) == 2
    assert result.merge is None


def test_both_runs_see_the_same_frames(tmp_path: Path) -> None:
    vlm = FakeVLM([*RUN_1, *RUN_2])
    run(vlm, tmp_path)
    first, second = vlm.calls[0].frames, vlm.calls[2].frames
    assert first == second


def test_a_segment_failing_twice_is_reported(tmp_path: Path) -> None:
    bad = "không phải JSON"
    vlm = FakeVLM([RUN_1[0], bad, bad, RUN_2[0], RUN_2[1]])
    result = run(vlm, tmp_path)
    assert result.failed_segments == ["VID-TEST-S002"]
    failed = json.loads((tmp_path / "run" / "failed_segments.json").read_text())
    assert [f["segment_id"] for f in failed] == ["VID-TEST-S002"]
    assert [p.step for p in result.profiles] == ["Nhặt cốc từ khay", "Đặt cốc vào thùng carton"]


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_one_pass_can_run_on_its_own(tmp_path: Path) -> None:
    pipeline = DescribePipeline(
        FakeVLM(RUN_1), process_id="PACK01", default_fps=4.0, max_frames=48, sampler=fake_sampler
    )
    first = pipeline.pass_a(segments(2), tmp_path / "a")
    assert len(first.steps) == 4
    assert pipeline.pass_b(first, first).steps  # a run agrees with itself
    with pytest.raises(ValueError, match="LLM"):
        pipeline.pass_c(first, segments(2), tmp_path)


def test_the_expert_words_reach_the_profiles_and_propose_reasons(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mentormind.processing.vlm.passes.reasons import propose_reasons
    from tests.processing.vlm.transcript.fakes import install_spec03, line

    install_spec03(monkeypatch)
    said = [
        line("Nhặt cốc lên nhé.", 0.5, 1.5),
        line("Đặt cốc vào thùng, xếp nghiêng để cốc không bị nứt.", 8, 10, label="factory_confidential"),
    ]
    result = run(FakeVLM(RUN_1), tmp_path, consistency=False, transcript=said)
    by_step = {p.step: p for p in result.profiles}
    # Spec 04 §3 (AC-22): both lines fall in segment 1, each goes to the step it is about.
    assert by_step["Nhặt cốc từ khay"].evidence.transcript_excerpt == "Nhặt cốc lên nhé."
    placing = by_step["Đặt cốc vào thùng carton"]
    assert placing.evidence.transcript_excerpt == "Đặt cốc vào thùng, xếp nghiêng để cốc không bị nứt."
    assert by_step["Kiểm tra nhãn"].evidence.transcript_excerpt is None  # segment 2: the expert said nothing
    # A profile quoting factory words is factory data, whatever its segment's label; the other is not.
    assert placing.data_classification == "factory_confidential"
    assert by_step["Nhặt cốc từ khay"].data_classification == "synthetic"
    llm = FakeLLM([{"has_reason": True, "purpose_span": "để cốc không bị nứt"}])
    reasoned, untouched = propose_reasons([placing, by_step["Nhặt cốc từ khay"]], llm)
    assert (reasoned.reason, reasoned.reason_source, reasoned.status) == (
        "Đặt cốc vào thùng, xếp nghiêng để cốc không bị nứt.",  # the expert's sentence (AC-26)
        "expert_verbal",
        "in_review",
    )
    # The same reason is not in the picking step's own words: refused there (AC-09).
    assert (untouched.reason, untouched.status) == (None, "draft")


def test_without_spec_03_the_profiles_have_no_excerpt_as_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.processing.vlm.transcript.fakes import line, remove_spec03

    remove_spec03(monkeypatch)

    result = run(FakeVLM(RUN_1), tmp_path, consistency=False, transcript=[line("Nhặt cốc lên nhé.", 0.5, 1.5)])
    assert {p.evidence.transcript_excerpt for p in result.profiles} == {None}
