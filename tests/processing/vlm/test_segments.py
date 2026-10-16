"""spec 04 FR-05 / AC-21 — ``describe --video``: spec 03 fixed windows, 3 keyframes each, a segments.json."""

from __future__ import annotations

from pathlib import Path

import cv2
import pytest

from mentormind.capture.video import VideoCapturePipeline, media
from mentormind.capture.video.store import read_segments, segments_path
from mentormind.core.config import Settings
from mentormind.core.providers.vlm.backends.fake import FakeVLM
from mentormind.core.schemas.common import DataClassification
from mentormind.core.schemas.video import Segment
from mentormind.processing.vlm.pipeline import DescribePipeline
from tests.capture.video.fakes import fake_ffmpeg, synthetic_video
from tests.processing.vlm.passes.test_describe import fake_sampler
from tests.processing.vlm.test_pipeline import RUN_1

SYNTHETIC = DataClassification.SYNTHETIC


@pytest.fixture(autouse=True)
def _no_ffmpeg(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_ffmpeg(monkeypatch)


def cut(video: Path, work: Path) -> list[Segment]:
    capture = VideoCapturePipeline(Settings(_env_file=None))
    return capture.run(
        video, work_dir=work, process_id="PACK01", classification=SYNTHETIC, method="fixed_window", transcribe=False
    ).segments


def test_ac_21_every_window_has_three_keyframes_and_the_segments_are_saved(tmp_path: Path) -> None:
    segments = cut(synthetic_video(tmp_path / "in.mp4", 25, size=(1280, 720)), tmp_path / "work")
    assert [(s.t_start, s.t_end) for s in segments] == [(0, 10), (10, 20), (20, 25)]
    for segment in segments:
        assert len(segment.keyframes) == 3, segment.segment_id
        for keyframe in segment.keyframes:
            image = cv2.imread(keyframe)
            assert image is not None
            assert max(image.shape[:2]) == 768  # spec 03 FR-05: long side 768 px
    assert read_segments(segments_path(tmp_path / "work", segments[0].video_id)) == segments


def test_ac_21_a_second_run_does_not_read_the_video_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    video = synthetic_video(tmp_path / "in.mp4", 12)
    first = cut(video, tmp_path / "work")
    monkeypatch.setattr(media.FrameReader, "at", lambda self, t: pytest.fail("keyframes are cached"))
    assert cut(video, tmp_path / "work") == first


def test_ac_21_profiles_carry_the_keyframes_of_their_segment(tmp_path: Path) -> None:
    segments = cut(synthetic_video(tmp_path / "in.mp4", 20), tmp_path / "work")
    pipeline = DescribePipeline(
        FakeVLM(RUN_1), process_id="PACK01", default_fps=4.0, max_frames=48, consistency=False, sampler=fake_sampler
    )
    profiles = pipeline.run(segments, tmp_path / "run").profiles
    assert profiles
    by_segment = {s.segment_id: s.keyframes for s in segments}
    for profile in profiles:
        expected = [k for sid in profile.evidence.segment_ids for k in by_segment[sid]]
        assert profile.evidence.keyframes == expected


def test_a_video_id_reads_back_the_saved_segments(tmp_path: Path) -> None:
    segments = cut(synthetic_video(tmp_path / "in.mp4", 10), tmp_path / "work")
    assert read_segments(segments_path(tmp_path / "work", segments[0].video_id)) == segments
    with pytest.raises(FileNotFoundError, match="--video"):
        read_segments(segments_path(tmp_path / "work", "VID-000000000000"))
