"""spec 04 T04-5 — pass C: merge across adjacent segments, never invent a step (AC-05)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mentormind.core.guard import ConfidentialDataError
from mentormind.core.providers.llm.backends.fake import FakeLLM
from mentormind.core.schemas import Actor
from mentormind.core.schemas.common import DataClassification
from mentormind.core.schemas.video import Segment
from mentormind.processing.vlm.passes import PassAResult, TimedStep
from mentormind.processing.vlm.passes.merge import merge_steps


def segment(i: int, label: DataClassification = DataClassification.SYNTHETIC) -> Segment:
    return Segment(
        segment_id=f"S{i}",
        video_id="VID-TEST",
        index=i,
        t_start=10.0 * (i - 1),
        t_end=10.0 * i,
        method="fixed_window",
        motion_score=None,
        keyframes=[f"kf{i}.jpg"],
        clip_path=f"c{i}.mp4",
        data_classification=label,
    )


SEGMENTS = [segment(1), segment(2), segment(3)]


def timed(name: str, start: float, end: float, seg: int, actor: Actor | None = "human") -> TimedStep:
    return TimedStep(
        segment_id=f"S{seg}", t_start=start, t_end=end, step=name, confidence=0.8, fps=4.0,
        keyframes=[f"kf{seg}.jpg"], actor=actor,
    )  # fmt: skip


INPUT = PassAResult(
    steps=[
        timed("Nhặt cốc từ khay", 2, 5, seg=1),
        timed("Đặt cốc vào thùng carton", 8, 10, seg=1),
        timed("Đặt cốc vào thùng", 10, 11.5, seg=2),
        timed("Đậy nắp đỏ", 25, 28, seg=3),
    ]
)


def run(answer: object, tmp_path: Path, steps: PassAResult = INPUT) -> tuple[PassAResult, object]:
    llm = FakeLLM([answer])  # type: ignore[list-item]
    return merge_steps(steps, SEGMENTS, llm, process_id="PACK01", work_dir=tmp_path)


def test_ac_05_an_invented_step_is_filtered_out(tmp_path: Path) -> None:
    answer = {
        "steps": [
            {"step": "Nhặt cốc từ khay", "source_ids": ["s1"]},
            {"step": "Kiểm tra chất lượng bằng mắt", "source_ids": []},  # not in the input
            {"step": "Quét mã vạch trên thùng", "source_ids": ["s99"]},  # unknown id
            {"step": "Đặt cốc vào thùng carton", "source_ids": ["s2", "s3"]},
            {"step": "Đậy nắp đỏ", "source_ids": ["s4"]},
        ]
    }
    result, report = run(answer, tmp_path)
    names = [s.step for s in result.steps]
    assert names == ["Nhặt cốc từ khay", "Đặt cốc vào thùng carton", "Đậy nắp đỏ"]
    assert report.invented_dropped == 2  # type: ignore[attr-defined]


def test_ac_05_an_invented_step_hiding_behind_a_real_id_is_rejected(tmp_path: Path) -> None:
    answer = {"steps": [{"step": "Dán nhãn cảnh báo lên thùng", "source_ids": ["s4"]}]}
    result, report = run(answer, tmp_path)
    assert "Dán nhãn cảnh báo lên thùng" not in [s.step for s in result.steps]
    assert [s.step for s in result.steps][-1] == "Đậy nắp đỏ"  # the source is kept as it was
    assert report.rejected == 1  # type: ignore[attr-defined]


def test_a_step_cut_by_a_segment_boundary_becomes_one_step(tmp_path: Path) -> None:
    answer = {"steps": [{"step": "Đặt cốc vào thùng carton", "source_ids": ["s2", "s3"]}]}
    result, _ = run(answer, tmp_path)
    merged = next(s for s in result.steps if s.step == "Đặt cốc vào thùng carton")
    assert (merged.t_start, merged.t_end) == (8, 11.5)
    assert merged.sources() == ["S1", "S2"]
    assert merged.keyframes == ["kf1.jpg", "kf2.jpg"]
    assert len(result.steps) == 3  # the two others are kept even though the LLM left them out
    assert (tmp_path / "pass_c.json").is_file()


def test_steps_of_non_adjacent_segments_are_not_merged(tmp_path: Path) -> None:
    answer = {"steps": [{"step": "Nhặt cốc từ khay", "source_ids": ["s1", "s4"]}]}
    result, report = run(answer, tmp_path)
    assert len(result.steps) == 4 and report.rejected == 1  # type: ignore[attr-defined]


def test_an_unreadable_answer_keeps_every_step(tmp_path: Path) -> None:
    result, report = run("xin lỗi", tmp_path)
    assert result.steps == INPUT.steps and report.error  # type: ignore[attr-defined]


def test_fewer_than_two_steps_need_no_llm_call(tmp_path: Path) -> None:
    llm = FakeLLM()
    one = PassAResult(steps=INPUT.steps[:1])
    merge_steps(one, SEGMENTS, llm, process_id="PACK01", work_dir=tmp_path)
    assert llm.calls == []


def test_factory_steps_never_reach_a_cloud_llm(tmp_path: Path) -> None:
    factory = [segment(1, DataClassification.FACTORY_CONFIDENTIAL), segment(2)]
    llm = FakeLLM(is_cloud=True)
    with pytest.raises(ConfidentialDataError):
        merge_steps(INPUT.model_copy(update={"steps": INPUT.steps[:3]}), factory, llm,
                    process_id="PACK01", work_dir=tmp_path)  # fmt: skip
    assert llm.calls == []


def test_ac_19_steps_of_different_actors_are_never_merged(tmp_path: Path) -> None:
    steps = PassAResult(
        steps=[
            timed("Đặt cốc vào thùng carton", 8, 10, seg=1, actor="human"),
            timed("Đặt cốc vào thùng carton", 10, 11, seg=2, actor="robot"),
        ]
    )
    answer = {"steps": [{"step": "Đặt cốc vào thùng carton", "source_ids": ["s1", "s2"]}]}
    result, report = run(answer, tmp_path, steps=steps)
    assert [s.actor for s in result.steps] == ["human", "robot"]
    assert report.rejected == 1  # type: ignore[attr-defined]


def test_ac_19_the_llm_cannot_change_who_performs_a_step(tmp_path: Path) -> None:
    steps = PassAResult(
        steps=[
            timed("Đặt cốc vào thùng carton", 8, 10, seg=1, actor=None),
            timed("Đặt cốc vào thùng", 10, 11, seg=2, actor="robot"),
        ]
    )
    answer = {"steps": [{"step": "Đặt cốc vào thùng carton", "source_ids": ["s1", "s2"], "actor": "human"}]}
    result, _ = run(answer, tmp_path, steps=steps)
    [merged] = result.steps
    assert merged.actor == "robot"  # from the sources, whatever the LLM wrote
    prompt = json.loads((tmp_path / "pass_c.json").read_text(encoding="utf-8"))["prompt"]
    assert '"actor": "robot"' in prompt  # the LLM is told who did each step
