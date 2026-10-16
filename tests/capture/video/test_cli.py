"""spec 03 — ``knowhow video probe|segment|transcribe|providers``."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mentormind.core.cli import app
from mentormind.core.config import get_settings
from tests.capture.video.fakes import fake_ffmpeg, synthetic_video

runner = CliRunner()


@pytest.fixture(autouse=True)
def _hermetic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("KNOWHOW_ASR_PROVIDER", "fake")
    monkeypatch.setenv("KNOWHOW_WORK_DIR", str(tmp_path / "work"))
    fake_ffmpeg(monkeypatch)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_providers_lists_the_local_asr_backends() -> None:
    result = runner.invoke(app, ["video", "providers"])
    assert result.exit_code == 0, result.output
    assert "faster_whisper" in result.output and "* fake" in result.output and "local" in result.output


def test_ac_17_providers_lists_remote_on_the_inference_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOWHOW_ASR_PROVIDER", "remote")
    monkeypatch.setenv("KNOWHOW_INFERENCE_URL", "https://team:s3cret@inference.example.com/v1")
    monkeypatch.setenv("KNOWHOW_LOCAL_HOSTS", "[]")
    get_settings.cache_clear()
    result = runner.invoke(app, ["video", "providers"])
    assert result.exit_code == 0, result.output
    assert "* remote" in result.output and "server" in result.output
    assert "máy chủ https://inference.example.com/v1 (cloud)" in result.output and "s3cret" not in result.output


def test_segment_writes_the_segments_and_reports_the_method(tmp_path: Path) -> None:
    video = synthetic_video(tmp_path / "in.mp4", 25)
    result = runner.invoke(
        app, ["video", "segment", str(video), "--method", "fixed_window", "--classification", "public"]
    )
    assert result.exit_code == 0, result.output
    assert "3 đoạn" in result.output and "fixed_window" in result.output
    assert list((tmp_path / "work" / "video").glob("VID-*/segments.json"))
    bad = runner.invoke(app, ["video", "segment", str(video), "--method", "magic"])
    assert bad.exit_code == 2 and "hand_activity" in bad.output


def test_probe_prints_the_video_asset(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["video", "probe", str(synthetic_video(tmp_path / "in.mp4", 6)), "--process-id", "PACK01"]
    )
    assert result.exit_code == 0, result.output
    assert '"duration_s": 6.0' in result.output and '"data_classification": "factory_confidential"' in result.output


def test_ac_08_recall_audio_for_an_unknown_video_fails_without_writing(tmp_path: Path) -> None:
    audio = tmp_path / "recall.m4a"
    audio.write_bytes(b"audio")
    result = runner.invoke(
        app, ["video", "transcribe", "--recall-audio", str(audio), "--video-id", "VID-ffffffffffff", "--offset", "12.5"]
    )
    assert result.exit_code == 1 and "VID-ffffffffffff" in result.output
    assert not (tmp_path / "work").exists()


def test_transcribe_a_silent_video_says_so(tmp_path: Path) -> None:
    result = runner.invoke(app, ["video", "transcribe", str(synthetic_video(tmp_path / "in.mp4", 4))])
    assert result.exit_code == 0 and "không có audio" in result.output
