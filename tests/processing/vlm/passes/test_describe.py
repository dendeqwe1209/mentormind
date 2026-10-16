"""spec 04 T04-3 — pass A: valid drafts (AC-01), no reason (AC-02), repair + failures (AC-06),
steps tiling their segment (AC-24), or keeping the model's spans by KNOWHOW_VLM_STEP_TIMES (AC-28)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, get_args

import pytest
from PIL import Image
from pydantic import ValidationError

from mentormind.core.config import Settings
from mentormind.core.guard import SupportsCloudFlag
from mentormind.core.providers.vlm.backends.fake import FakeVLM
from mentormind.core.schemas.common import DataClassification
from mentormind.core.schemas.video import Segment
from mentormind.core.schemas.work_profile import validate_against_contract
from mentormind.processing.vlm.frames import SampledFrames
from mentormind.processing.vlm.passes import describe_segments, to_work_profiles
from mentormind.processing.vlm.passes.step_times import (
    STEP_TIMERS,
    ModelSpans,
    SegmentTiling,
    StepTimer,
    get_step_timer,
)


def segments(n: int = 3) -> list[Segment]:
    return [
        Segment(
            segment_id=f"VID-TEST-S{i:03d}",
            video_id="VID-TEST",
            index=i,
            t_start=10.0 * (i - 1),
            t_end=10.0 * i,
            method="fixed_window",
            motion_score=None,
            keyframes=[f"kf_{i}.jpg"],
            clip_path=f"clip_{i}.mp4",
            data_classification=DataClassification.SYNTHETIC,
        )
        for i in range(1, n + 1)
    ]


def fake_sampler(
    segment: Segment,
    destination: SupportsCloudFlag,
    *,
    out_dir: Path,
    default_fps: float,
    max_frames: int,
) -> SampledFrames:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(3):
        path = out_dir / f"f{i}.jpg"
        Image.new("RGB", (32, 18), (i * 60, 90, 120)).save(path)
        paths.append(path)
    return SampledFrames(paths=paths, timestamps=[0.0, 1.0, 2.0], fps=default_fps)


def step(name: str, start: float, end: float, **extra: Any) -> dict[str, Any]:
    return {
        "step": name,
        "hand_action": "tay phải",
        "objects": ["cốc"],
        "key_point_observed": None,
        "t_start_rel": start,
        "t_end_rel": end,
        "confidence": 0.8,
        **extra,
    }


def run(vlm: FakeVLM, tmp_path: Path, **kwargs: Any) -> Any:
    return describe_segments(
        segments(),
        vlm,
        process_id="PACK01",
        work_dir=tmp_path,
        default_fps=4.0,
        max_frames=48,
        sampler=fake_sampler,
        **kwargs,
    )


def test_ac_01_three_segments_become_valid_drafts_numbered_from_one(tmp_path: Path) -> None:
    vlm = FakeVLM(
        [
            {"steps": [step("Nhặt cốc", 0, 2), step("Đặt cốc vào thùng", 2, 5)]},
            {"steps": [step("Đậy nắp đỏ", 1, 4)]},
            {"steps": [step("Dồn cốc thành hàng", 0, 3)]},
        ]
    )
    result = run(vlm, tmp_path)
    profiles = to_work_profiles(result, segments=segments(), process_id="PACK01", provider=vlm, model=vlm.model)
    assert [p.step_order for p in profiles] == [1, 2, 3, 4]
    assert profiles[0].profile_id == "WP-PACK01-001"
    for profile in profiles:
        validate_against_contract(profile)
        assert (profile.status, profile.generated_by) == ("draft", "vlm")
    second = profiles[2]
    assert (second.evidence.t_start, second.evidence.t_end) == (10.0, 20.0)  # the only step: whole segment
    assert second.evidence.segment_ids == ["VID-TEST-S002"]
    assert second.model_info is not None and second.model_info.fps == 4.0
    assert (tmp_path / "pass_a" / "VID-TEST-S001.json").is_file()  # FR-06 raw answer kept


def test_ac_02_reason_from_the_model_is_dropped(tmp_path: Path) -> None:
    sneaky = step("Đặt cốc vào thùng", 0, 3, reason="để tránh trầy", reason_source="expert_verbal")
    vlm = FakeVLM([{"steps": [sneaky]}])
    result = run(vlm, tmp_path)
    profiles = to_work_profiles(result, segments=segments(), process_id="PACK01", provider=vlm, model=vlm.model)
    assert profiles and all(p.reason is None and p.reason_source is None for p in profiles)


def test_ac_06_twice_invalid_json_is_logged_and_others_continue(tmp_path: Path) -> None:
    ok = {"steps": [step("Nhặt cốc", 0, 2)]}
    vlm = FakeVLM([ok, "xin lỗi, tôi không chắc", '{"steps": [{"step": 1}]}', ok])
    result = run(vlm, tmp_path)
    assert [s.segment_id for s in result.steps] == ["VID-TEST-S001", "VID-TEST-S003"]
    failed = json.loads((tmp_path / "failed_segments.json").read_text())
    assert [f["segment_id"] for f in failed] == ["VID-TEST-S002"]
    assert "LƯU Ý" in vlm.calls[2].prompt  # the retry used the repair prompt
    assert len(vlm.calls) == 4


def test_repair_prompt_recovers_a_segment(tmp_path: Path) -> None:
    ok = {"steps": [step("Nhặt cốc", 0, 2)]}
    vlm = FakeVLM([ok, "không phải JSON", ok, ok])
    result = run(vlm, tmp_path)
    assert len(result.steps) == 3 and result.failed == []
    assert not (tmp_path / "failed_segments.json").exists()


def test_relative_times_are_clamped_to_the_segment(tmp_path: Path) -> None:
    # A start past the segment end is clamped to it and shares the span of the group before.
    steps = [step("Nhặt cốc", 2, 3), step("Đặt cốc vào thùng", 5, 6), step("Đậy nắp thùng", 12, 25)]
    vlm = FakeVLM([{"steps": steps}])
    result = run(vlm, tmp_path)
    spans = [(s.t_start, s.t_end) for s in result.steps if s.segment_id == "VID-TEST-S001"]
    assert spans == [(0.0, 5.0), (5.0, 10.0), (5.0, 10.0)]


def test_ac_24_steps_tile_their_segment_in_start_order(tmp_path: Path) -> None:
    # LASI video 2026-10-08: the model points at the instant it sees an action (116.9-117.0 s), so
    # the review page played ~1 s per step and pass B dropped same-name steps a few tenths apart.
    vlm = FakeVLM(
        [
            {  # out of order, instantaneous spans
                "steps": [
                    step("Đặt cốc vào thùng", 6.9, 7.0),
                    step("Nhặt cốc", 2.1, 2.2),
                    step("Đậy nắp thùng", 8.4, 8.4),
                ]
            },
            {"steps": [step("Dán nhãn lên thùng", 4.0, 4.1)]},
            {"steps": [step("Nhặt cốc", 3.0, 3.1), step("Xoay cốc", 3.0, 3.0), step("Đặt cốc vào khay", 6.0, 6.5)]},
        ]
    )
    result = run(vlm, tmp_path)
    assert [(s.segment_id[-1], s.step, s.t_start, s.t_end) for s in result.steps] == [
        ("1", "Nhặt cốc", 0.0, 6.9),  # the first step opens the segment
        ("1", "Đặt cốc vào thùng", 6.9, 8.4),  # ... each ends when the next one starts
        ("1", "Đậy nắp thùng", 8.4, 10.0),  # ... the last closes it
        ("2", "Dán nhãn lên thùng", 10.0, 20.0),  # one step: the whole segment
        ("3", "Nhặt cốc", 20.0, 26.0),  # same start: same span, the model's order kept
        ("3", "Xoay cốc", 20.0, 26.0),
        ("3", "Đặt cốc vào khay", 26.0, 30.0),
    ]
    assert all(s.t_end > s.t_start for s in result.steps)


# One answer, repeated by the fake for each segment: out of order, one end past the segment end,
# one end before its start.
TIMED = {
    "steps": [
        step("Đặt cốc vào thùng", 6.9, 7.0),
        step("Nhặt cốc", 2.1, 2.2),
        step("Đậy nắp thùng", 8.4, 25),
        step("Xoay cốc", 5.0, 4.0),
    ]
}
#: Segment S002 (10-20 s) of TIMED, per KNOWHOW_VLM_STEP_TIMES.
TIMED_S002 = {
    # The model's spans, clamped as pass A did before spec 04 v1.22, in the model's order.
    "model": [
        ("Đặt cốc vào thùng", 16.9, 17.0),
        ("Nhặt cốc", 12.1, 12.2),
        ("Đậy nắp thùng", 18.4, 20.0),
        ("Xoay cốc", 15.0, 15.0),
    ],
    # The same steps tiling the segment in start order (AC-24).
    "segment": [
        ("Nhặt cốc", 10.0, 15.0),
        ("Xoay cốc", 15.0, 16.9),
        ("Đặt cốc vào thùng", 16.9, 18.4),
        ("Đậy nắp thùng", 18.4, 20.0),
    ],
}


@pytest.mark.parametrize(("env", "mode"), [(None, "segment"), ("segment", "segment"), ("model", "model")])
def test_ac_28_step_times_follow_knowhow_vlm_step_times(
    env: str | None, mode: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if env is None:
        monkeypatch.delenv("KNOWHOW_VLM_STEP_TIMES", raising=False)
    else:
        monkeypatch.setenv("KNOWHOW_VLM_STEP_TIMES", env)
    settings = Settings(_env_file=None)
    assert settings.vlm_step_times == mode  # unset: segment, it matched the hand labels better
    timer = get_step_timer(settings.vlm_step_times)
    assert isinstance(timer, {"segment": SegmentTiling, "model": ModelSpans}[mode])
    result = run(FakeVLM([TIMED]), tmp_path, step_timer=timer)
    spans = [(s.step, s.t_start, s.t_end) for s in result.steps if s.segment_id == "VID-TEST-S002"]
    assert spans == TIMED_S002[mode]


def test_ac_28_pass_a_tiles_when_no_timer_is_given(tmp_path: Path) -> None:
    result = run(FakeVLM([TIMED]), tmp_path)
    spans = [(s.step, s.t_start, s.t_end) for s in result.steps if s.segment_id == "VID-TEST-S002"]
    assert spans == TIMED_S002["segment"]


def test_ac_28_model_spans_are_clamped_into_the_segment(tmp_path: Path) -> None:
    # Pass A before spec 04 v1.22: a start past the end is cut at the segment end too.
    vlm = FakeVLM([{"steps": [step("Nhặt cốc", 8, 25), step("Đậy nắp thùng", 12, 13)]}])
    result = run(vlm, tmp_path, step_timer=ModelSpans())
    spans = [(s.t_start, s.t_end) for s in result.steps if s.segment_id == "VID-TEST-S001"]
    assert spans == [(8.0, 10.0), (10.0, 10.0)]


def test_ac_28_an_unknown_step_times_value_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOWHOW_VLM_STEP_TIMES", "auto")
    with pytest.raises(ValidationError, match="vlm_step_times"):
        Settings(_env_file=None)
    with pytest.raises(ValueError, match="segment, model"):
        get_step_timer("auto")


def test_ac_28_every_settings_value_names_a_registered_timer() -> None:
    names = get_args(Settings.model_fields["vlm_step_times"].annotation)
    assert names == tuple(STEP_TIMERS) == ("segment", "model")
    for name in names:
        timer = get_step_timer(name)
        assert isinstance(timer, StepTimer) and timer.name == name


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_objects_given_as_one_string_become_a_list(tmp_path: Path) -> None:
    """DashScope's json_object mode returned "objects": "linh kiện, hộp" on the LASI video."""
    vlm = FakeVLM([{"steps": [step("Đặt linh kiện vào hộp", 0, 2, objects="linh kiện, hộp")]}])
    result = run(vlm, tmp_path)
    assert result.failed == [] and result.steps[0].objects == ["linh kiện", "hộp"]


@pytest.mark.parametrize(
    ("said", "actor"),
    [
        ("human", "human"),
        ("robot", "robot"),
        ("machine", "machine"),
        ("công nhân", "human"),
        ("kỹ sư", "human"),
        ("worker", "human"),
        ("robot SCARA", "robot"),
        ("máy dựng thùng", "machine"),
        ("không rõ", None),
        (None, None),
    ],
)
def test_ac_18_pass_a_reads_who_performs_the_step(said: str | None, actor: str | None, tmp_path: Path) -> None:
    vlm = FakeVLM([{"steps": [step("Đặt cốc vào thùng", 0, 2, actor=said)]}])
    result = run(vlm, tmp_path)
    assert result.failed == [] and result.steps[0].actor == actor
    profiles = to_work_profiles(result, segments=segments(), process_id="PACK01", provider=vlm, model=vlm.model)
    for profile in profiles:  # the fake repeats its answer for each of the 3 segments
        assert profile.actor == actor
        validate_against_contract(profile)


def test_ac_18_pass_a_asks_for_the_actor() -> None:
    from mentormind.processing.vlm.passes.describe import PASS_A_SCHEMA
    from mentormind.processing.vlm.passes.prompting import render_prompt

    item = PASS_A_SCHEMA["properties"]["steps"]["items"]
    assert item["properties"]["actor"]["enum"] == ["human", "robot", "machine", None]
    assert "actor" in item["required"]
    prompt = render_prompt("pass_a_describe.md", process_id="PACK01", duration="10.0", fps="4", timestamps="0.0")
    assert '"actor"' in prompt and "human" in prompt and "robot" in prompt


def test_ac_20_an_english_answer_is_asked_again_in_vietnamese(tmp_path: Path) -> None:
    # LASI sweep 2026-10-04: the Q4 model on Ollama answered 63-83% of the step names in English.
    english = {"scene": "x", "steps": [step("Pick product", 0, 1, hand_action="right hand picks it")]}
    vietnamese = {"scene": "x", "steps": [step("Nhặt sản phẩm", 0, 1)]}
    vlm = FakeVLM([english, vietnamese, {"steps": []}, {"steps": []}])
    result = run(vlm, tmp_path)
    assert [s.step for s in result.steps] == ["Nhặt sản phẩm"]
    assert "tiếng Việt" in vlm.calls[1].prompt and "steps[0].step" in vlm.calls[1].prompt
    assert len(vlm.calls) == 4  # one repair, for the first segment only


def test_ac_20_an_english_answer_is_kept_when_the_repair_fails(tmp_path: Path) -> None:
    english = {"scene": "x", "steps": [step("Pick product", 0, 1)]}
    vlm = FakeVLM([english, "không phải JSON", {"steps": []}, {"steps": []}])
    result = run(vlm, tmp_path)
    assert [s.step for s in result.steps] == ["Pick product"] and result.failed == []


def test_ac_20_pass_a_asks_for_vietnamese() -> None:
    from mentormind.processing.vlm.passes.prompting import render_prompt

    prompt = render_prompt("pass_a_describe.md", process_id="PACK01", duration="10.0", fps="4", timestamps="0.0")
    assert "TIẾNG VIỆT" in prompt
