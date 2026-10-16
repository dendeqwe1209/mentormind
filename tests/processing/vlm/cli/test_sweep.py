"""spec 04 §6, AC-28 — ``knowhow vlm sweep`` places the steps by KNOWHOW_VLM_STEP_TIMES and says so."""

from __future__ import annotations

import csv
import functools
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mentormind.capture.video import video_id_for
from mentormind.core.providers.vlm.backends.fake import FakeVLM
from mentormind.processing.vlm import sweep
from mentormind.processing.vlm.cli import app
from mentormind.processing.vlm.passes import PassAResult
from tests.processing.vlm.passes.test_describe import TIMED, TIMED_S002, fake_sampler, segments

runner = CliRunner()


@pytest.mark.parametrize("mode", ["segment", "model"])
def test_ac_28_vlm_sweep_follows_knowhow_vlm_step_times(
    mode: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KNOWHOW_VLM_STEP_TIMES", mode)
    monkeypatch.setattr("mentormind.core.providers.vlm.get_vlm_provider", lambda settings: FakeVLM([TIMED]))
    # Only the frames are faked: the CLI picks the step timer itself.
    monkeypatch.setattr(sweep, "run_sweep", functools.partial(sweep.run_sweep, sampler=fake_sampler))
    video = tmp_path / "video.mp4"
    video.write_bytes(b"not a real video: --segments skips the cutting")
    seg_file = tmp_path / "segments.json"
    seg_file.write_text(json.dumps([s.model_dump(mode="json") for s in segments(2)]), encoding="utf-8")
    truth = tmp_path / "truth.json"
    truth.write_text(json.dumps([{"step": "Nhặt cốc", "t_start": 10, "t_end": 15}]), encoding="utf-8")
    args = ["--video", str(video), "--truth", str(truth), "--segments", str(seg_file), "--fps", "1"]
    result = runner.invoke(app, ["sweep", *args, "--out", "sweep.csv"])
    assert result.exit_code == 0, result.output
    # One detail folder per mode, so a sweep per value does not overwrite the other one.
    run_dir = Path("data/work/vlm") / video_id_for(video) / f"sweep-fake-{mode}" / "fps1"
    predictions = PassAResult.model_validate_json((run_dir / "predictions.json").read_text(encoding="utf-8"))
    spans = [(s.step, s.t_start, s.t_end) for s in predictions.steps if s.segment_id == "VID-TEST-S002"]
    assert spans == TIMED_S002[mode]
    with Path("sweep.csv").open(encoding="utf-8") as handle:
        assert [row["step_times"] for row in csv.DictReader(handle)] == [mode]
    assert f"| {mode} |" in Path("sweep.md").read_text(encoding="utf-8")
