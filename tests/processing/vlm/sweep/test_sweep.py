"""spec 04 T04-6 — matching rule, metrics, the CSV of AC-07, truth file, fixed windows; AC-28."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from mentormind.core.config import REPO_ROOT
from mentormind.core.guard import SupportsCloudFlag
from mentormind.core.providers.vlm.backends.fake import FakeVLM
from mentormind.core.schemas.common import DataClassification
from mentormind.core.schemas.video import Segment
from mentormind.processing.vlm.frames import SampledFrames
from mentormind.processing.vlm.passes import PassAResult
from mentormind.processing.vlm.passes.step_times import ModelSpans, SegmentTiling, StepTimer
from mentormind.processing.vlm.sweep import (
    CSV_COLUMNS,
    TruthStep,
    actor_accuracy,
    load_truth,
    markdown_table,
    match_steps,
    order_accuracy,
    run_sweep,
    write_csv,
)
from tests.processing.vlm.passes.test_describe import TIMED, TIMED_S002

REPO = REPO_ROOT


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


def test_matching_needs_similar_text_and_overlapping_time() -> None:
    truth = [
        TruthStep(step="Đậy nắp đỏ lên sản phẩm", t_start=10, t_end=15),
        TruthStep(step="Đặt cốc vào thùng carton", t_start=20, t_end=25),
    ]
    predicted = [
        _timed("Đậy nắp đỏ lên cốc sản phẩm", 11, 13),  # similar + overlap -> match
        _timed("Đặt cốc vào thùng carton", 40, 45),  # similar but no overlap -> no match
    ]
    matches = match_steps(truth, predicted)
    assert [(m.truth_index, m.predicted_index) for m in matches] == [(0, 0)]


def test_order_accuracy_is_normalised_kendall_tau() -> None:
    truth = [TruthStep(step=f"Bước số {i}", t_start=i * 10, t_end=i * 10 + 9) for i in range(3)]
    in_order = [_timed(f"Bước số {i}", i * 10 + 1, i * 10 + 2) for i in range(3)]
    assert order_accuracy(match_steps(truth, in_order), in_order) == 1.0


def test_ac_07_sweep_writes_every_required_column(tmp_path: Path) -> None:
    truth_file = tmp_path / "truth.json"
    truth_file.write_text(
        json.dumps(
            [
                {"step": "Nhặt cốc", "t_start": 0, "t_end": 3, "key_point": "cầm thân cốc"},
                {"step": "Đặt cốc vào thùng", "t_start": 10, "t_end": 15},
            ]
        ),
        encoding="utf-8",
    )
    answer = {"steps": [step("Nhặt cốc", 0, 2, key_point_observed="cầm thân cốc"), step("Lau bàn", 3, 4)]}
    vlm = FakeVLM([answer])
    rows = run_sweep(
        segments(1),
        load_truth(truth_file),
        [1, 2],
        vlm,
        process_id="PACK01",
        work_dir=tmp_path / "work",
        max_frames=48,
        sampler=fake_sampler,
    )
    out = tmp_path / "sweep.csv"
    write_csv(rows, out)
    with out.open(encoding="utf-8") as handle:
        table = list(csv.DictReader(handle))
    required = {"fps", "recall", "precision", "order_accuracy", "key_point_recall"}
    assert required | {"tokens_used", "latency_s"} <= set(table[0]) == set(CSV_COLUMNS)
    assert [r["fps"] for r in table] == ["1.0", "2.0"]
    assert (float(table[0]["recall"]), float(table[0]["precision"])) == (0.5, 0.5)
    assert float(table[0]["key_point_recall"]) == 1.0
    assert (tmp_path / "work" / "fps1" / "profiles_draft.json").is_file()
    assert "actor_accuracy" in table[0]


@pytest.mark.parametrize(("timer", "mode"), [(None, "segment"), (SegmentTiling(), "segment"), (ModelSpans(), "model")])
def test_ac_28_sweep_places_steps_with_its_timer_and_records_it(
    timer: StepTimer | None, mode: str, tmp_path: Path
) -> None:
    extra = {} if timer is None else {"step_timer": timer}
    rows = run_sweep(
        segments(2),
        [TruthStep(step="Nhặt cốc", t_start=10, t_end=15)],
        [1],
        FakeVLM([TIMED]),
        process_id="PACK01",
        work_dir=tmp_path / "work",
        max_frames=48,
        sampler=fake_sampler,
        **extra,
    )
    saved = (tmp_path / "work" / "fps1" / "predictions.json").read_text(encoding="utf-8")
    steps = PassAResult.model_validate_json(saved).steps
    spans = [(s.step, s.t_start, s.t_end) for s in steps if s.segment_id == "VID-TEST-S002"]
    assert spans == TIMED_S002[mode]
    assert [r.step_times for r in rows] == [mode]
    assert f"| {mode} |" in markdown_table(rows)


def test_repo_groundtruth_file_loads() -> None:
    truth = load_truth(REPO / "data" / "video" / "groundtruth.json")
    assert len(truth) >= 20
    assert all(t.t_end >= t.t_start for t in truth)


def _timed(name: str, start: float, end: float, actor: str | None = None) -> Any:
    from mentormind.processing.vlm.passes import TimedStep

    return TimedStep(segment_id="S", t_start=start, t_end=end, step=name, confidence=0.9, fps=4.0, actor=actor)


def test_truth_workers_and_engineers_count_as_human() -> None:
    truth = [
        TruthStep(step="Đậy nắp đỏ", t_start=0, t_end=2, actor="worker"),
        TruthStep(step="Chỉnh cơ cấu dẫn hướng", t_start=5, t_end=7, actor="engineer"),
        TruthStep(step="Gắp cụm cốc", t_start=10, t_end=12, actor="robot"),
        TruthStep(step="Dựng thùng", t_start=15, t_end=17, actor="machine"),
    ]
    assert [t.actor for t in truth] == ["human", "human", "robot", "machine"]


def test_actor_accuracy_is_judged_on_time_whatever_the_wording() -> None:
    truth = [
        TruthStep(step="Đậy nắp đỏ lên sản phẩm", t_start=0, t_end=2, actor="worker"),
        TruthStep(step="Gắp cụm cốc vào thùng", t_start=10, t_end=12, actor="robot"),
        TruthStep(step="Dựng thùng carton", t_start=20, t_end=22, actor="machine"),
        TruthStep(step="Không ai đoán tới", t_start=30, t_end=32, actor="worker"),
    ]
    predicted = [
        _timed("Ấn nắp", 0.5, 1.5, actor="human"),  # right actor, different words
        _timed("Đặt sản phẩm vào hộp", 10, 12, actor="human"),  # wrong: it was the robot
        _timed("Mở thùng", 20, 22, actor=None),  # no actor: not judged
    ]
    assert actor_accuracy(truth, predicted) == 0.5
    assert actor_accuracy(truth, []) is None


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_fixed_windows_merge_a_short_tail() -> None:
    from mentormind.capture.video.postprocess import postprocess
    from mentormind.capture.video.segmenters import Cut, window_bounds

    def windows(duration: float) -> list[tuple[float, float]]:
        cuts = postprocess([Cut(*b) for b in window_bounds(duration, 10.0)], duration)
        return [(c.t_start, c.t_end) for c in cuts]

    assert windows(25.0) == [(0.0, 10.0), (10.0, 20.0), (20.0, 25.0)]
    assert windows(21.5) == [(0.0, 10.0), (10.0, 21.5)]  # 1.5 s tail merged (spec 03 FR-04)
