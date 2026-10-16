"""spec 03 FR-01 (probe) and FR-04 (post-processing, AC-02, AC-03)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from mentormind.capture.video.postprocess import MAX_S, MIN_S, PART_S, postprocess
from mentormind.capture.video.probe import probe_video
from mentormind.capture.video.segmenters import Cut
from mentormind.core.schemas.common import DataClassification
from tests.capture.video.fakes import synthetic_video

SYNTHETIC = DataClassification.SYNTHETIC


def test_probe_reads_ffprobe(tmp_path: Path) -> None:
    video = synthetic_video(tmp_path / "in.mp4", 2)
    info = {
        "format": {"duration": "193.793"},
        "streams": [{"codec_type": "video", "avg_frame_rate": "30000/1001"}, {"codec_type": "audio"}],
    }
    asset = probe_video(video, process_id="PACK01", classification=SYNTHETIC, read_streams=lambda v: info)
    assert (asset.duration_s, asset.fps, asset.has_audio, asset.process_id) == (193.793, 29.97, True, "PACK01")
    assert asset.video_id == "VID-" + hashlib.sha256(video.read_bytes()).hexdigest()[:12]
    assert asset.data_classification == SYNTHETIC


def test_without_ffprobe_opencv_reads_it_as_silent(tmp_path: Path) -> None:
    asset = probe_video(
        synthetic_video(tmp_path / "in.mp4", 6), process_id=None, classification=SYNTHETIC, read_streams=lambda v: None
    )
    assert (asset.duration_s, asset.fps, asset.has_audio) == (6.0, 4.0, False)
    with pytest.raises(FileNotFoundError):
        probe_video(tmp_path / "missing.mp4", process_id=None, classification=SYNTHETIC)
    with pytest.raises(ValueError, match="luồng hình"):
        probe_video(
            tmp_path / "in.mp4", process_id=None, classification=SYNTHETIC, read_streams=lambda v: {"streams": []}
        )


CASES = {
    "short pieces": [Cut(0, 1), Cut(1, 2.5), Cut(2.5, 9), Cut(9, 10.2), Cut(10.2, 30)],
    "one long shot": [Cut(0, 61)],
    "gaps and overlaps": [Cut(0.5, 8), Cut(7, 15), Cut(18, 22), Cut(21, 44)],
    "nothing detected": [],
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_ac_02_no_segment_shorter_than_3s_or_longer_than_20s(name: str) -> None:
    duration = 61.0 if name != "gaps and overlaps" else 44.0
    out = postprocess(CASES[name], duration)
    assert out and all(MIN_S <= c.duration <= MAX_S for c in out), [(c.t_start, c.t_end) for c in out]
    assert all(
        c.duration <= PART_S + 1e-9 for c in out if any(o.duration > MAX_S for o in CASES[name]) and c.duration > 10
    )


@pytest.mark.parametrize("name", sorted(CASES))
def test_ac_03_segments_are_back_to_back_and_cover_the_video(name: str) -> None:
    duration = 61.0 if name != "gaps and overlaps" else 44.0
    out = postprocess(CASES[name], duration)
    assert out[0].t_start == 0 and out[-1].t_end == pytest.approx(duration)
    assert all(a.t_end == pytest.approx(b.t_start) for a, b in zip(out, out[1:], strict=False))
    assert sum(c.duration for c in out) >= 0.95 * duration


def test_a_video_shorter_than_3s_is_one_segment_and_motion_is_duration_weighted() -> None:
    assert [(c.t_start, c.t_end) for c in postprocess([Cut(0, 1), Cut(1, 2.4)], 2.4)] == [(0, 2.4)]
    [merged] = postprocess([Cut(0, 2, motion_score=1.0), Cut(2, 8, motion_score=0.2)], 8)
    assert merged.motion_score == pytest.approx((2 * 1.0 + 6 * 0.2) / 8, abs=1e-3)
