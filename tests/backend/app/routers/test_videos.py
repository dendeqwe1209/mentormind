"""spec 08 §2, AC-13..AC-18 — video upload + processing, and the Sigma lots behind the RCA page.

No ffmpeg, no model, no network: clips are small synthetic videos (``tests.capture.video.fakes``),
the cutting methods, the ASR, the VLM and the LLM are fakes injected through
``videos.capture_pipeline`` and the provider factories. ``TestClient`` runs the background job
before ``post`` returns, so the job is finished when it is read back.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mentormind.agents.adapters import rest as rest_adapter
from mentormind.agents.adapters.factory import _sigma
from mentormind.backend.app.deps import get_profile_store
from mentormind.backend.app.main import app
from mentormind.backend.app.routers import sigma as sigma_router
from mentormind.backend.app.routers import videos as videos_router
from mentormind.capture.video import VideoCapturePipeline
from mentormind.capture.video.segmenters import (
    FixedWindowSegmenter,
    HandActivitySegmenter,
    Method,
    SceneSegmenter,
    Segmenter,
    SegmenterUnavailable,
)
from mentormind.core.config import Settings
from mentormind.core.providers import llm as llm_providers
from mentormind.core.providers import vlm as vlm_providers
from mentormind.core.providers.asr import ASRSegment
from mentormind.core.providers.asr.backends.fake import FakeASR
from mentormind.core.providers.llm.backends.fake import FakeLLM
from mentormind.core.providers.vlm.backends.fake import FakeVLM
from mentormind.core.schemas import VideoAsset
from mentormind.knowledge_base.sigma.adapter import CsvSigmaAdapter
from mentormind.knowledge_base.store.profile_store import ProfileStore
from tests.capture.video.fakes import fake_ffmpeg, synthetic_video
from tests.capture.video.test_transcribe_and_align import fake_extract
from tests.processing.vlm.test_pipeline import RUN_1, RUN_2

MERGE = {
    "steps": [
        {"step": "Nhặt cốc từ khay", "source_ids": ["s1"]},
        {"step": "Đặt cốc vào thùng carton", "source_ids": ["s2", "s3"]},
    ]
}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        work_dir=tmp_path / "work",
        profile_db=tmp_path / "profiles.sqlite",
        profile_sink="store",
        guard_audit_dir=tmp_path / "audit",
    )


@pytest.fixture
def store(settings: Settings) -> ProfileStore:
    return ProfileStore(db_path=str(settings.profile_db))


class Capture:
    """What the API's spec 03 pipeline runs with in these tests; each test may change it."""

    def __init__(self) -> None:
        self.speech: list[ASRSegment] = []
        self.build: Callable[[Method], Segmenter] = lambda method: FixedWindowSegmenter(motion=False)

    def pipeline(self, settings: Settings) -> VideoCapturePipeline:
        return VideoCapturePipeline(settings, build=self.build, asr=lambda: FakeASR(self.speech), extract=fake_extract)


@pytest.fixture
def capture(monkeypatch: pytest.MonkeyPatch) -> Capture:
    fakes = Capture()
    monkeypatch.setattr(videos_router, "capture_pipeline", fakes.pipeline)
    return fakes


@pytest.fixture
def client(
    settings: Settings, store: ProfileStore, capture: Capture, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    fake_ffmpeg(monkeypatch)
    monkeypatch.setattr(videos_router, "get_settings", lambda: settings)
    # The RCA/assistant routers read settings through the REST adapter: hermetic too (mock agents),
    # whatever KNOWHOW_API_AGENTS a developer .env sets.
    monkeypatch.setattr(rest_adapter, "get_settings", lambda: settings)
    monkeypatch.setattr(vlm_providers, "get_vlm_provider", lambda s=None: FakeVLM([*RUN_1, *RUN_2]))
    monkeypatch.setattr(llm_providers, "get_llm_provider", lambda s=None: FakeLLM([MERGE]))
    app.dependency_overrides[get_profile_store] = lambda: store
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _upload(client: TestClient, video: Path, *, classification: str | None = "synthetic", name: str = "") -> Any:
    data = {"process_id": "PACK01"} | ({} if classification is None else {"classification": classification})
    files = {"file": (name or video.name, video.read_bytes(), "video/mp4")}
    return client.post("/videos", files=files, data=data)


def test_ac_13_upload_keeps_the_video_under_its_content_id(
    client: TestClient, settings: Settings, tmp_path: Path
) -> None:
    video = synthetic_video(tmp_path / "pack.mp4", 20)
    res = _upload(client, video)
    assert res.status_code == 200, res.text
    asset = VideoAsset.model_validate(res.json())
    assert asset.video_id == "VID-" + hashlib.sha256(video.read_bytes()).hexdigest()[:12]
    assert (asset.process_id, asset.data_classification, asset.duration_s) == ("PACK01", "synthetic", 20.0)
    folder = settings.work_dir / "video" / asset.video_id
    assert (folder / "source.mp4").read_bytes() == video.read_bytes()
    assert VideoAsset.model_validate_json((folder / "video.json").read_text(encoding="utf-8")) == asset


@pytest.mark.parametrize(
    ("classification", "name"), [(None, "pack.mp4"), ("secret", "pack.mp4"), ("synthetic", "notes.txt")]
)
def test_ac_13_no_label_or_no_video_is_refused_and_nothing_is_kept(
    client: TestClient, settings: Settings, tmp_path: Path, classification: str | None, name: str
) -> None:
    res = _upload(client, synthetic_video(tmp_path / "pack.mp4", 4), classification=classification, name=name)
    assert res.status_code == 422
    videos = settings.work_dir / "video"
    assert not videos.exists() or not list(videos.glob("VID-*"))


def test_ac_14_processing_saves_drafts_segments_and_progress(
    client: TestClient, settings: Settings, tmp_path: Path
) -> None:
    video_id = _upload(client, synthetic_video(tmp_path / "pack.mp4", 20)).json()["video_id"]
    job_id = client.post(f"/videos/{video_id}/process", json={}).json()["job_id"]
    job = client.get(f"/jobs/{job_id}").json()
    assert job["status"] == "done", job
    result = job["result"]
    assert (result["video_id"], result["segments"], result["transcript_lines"]) == (video_id, 2, 0)
    assert result["method"] == "hand_activity"  # the default
    drafts = {p["profile_id"]: p for p in client.get("/profiles", params={"process_id": "PACK01"}).json()}
    assert result["profiles"] and set(result["profiles"]) <= set(drafts)
    for profile_id in result["profiles"]:
        profile = drafts[profile_id]
        assert profile["status"] == "draft" and profile["reason"] is None
        assert profile["evidence"]["video_id"] == video_id and profile["evidence"]["keyframes"]
    segments = client.get(f"/videos/{video_id}/segments").json()
    assert [s["segment_id"] for s in segments] == [f"{video_id}-S001", f"{video_id}-S002"]
    assert all(len(s["keyframes"]) == 3 for s in segments)


def test_ac_14_unknown_video_or_method_is_refused(client: TestClient, tmp_path: Path) -> None:
    assert client.post("/videos/VID-000000000000/process", json={}).status_code == 404
    assert client.post("/videos/..%2F..%2Fetc/process", json={}).status_code == 404
    assert client.get("/videos/VID-000000000000/segments").status_code == 404
    video_id = _upload(client, synthetic_video(tmp_path / "pack.mp4", 4)).json()["video_id"]
    res = client.post(f"/videos/{video_id}/process", json={"method": "magic"})
    assert res.status_code == 422 and "hand_activity" in res.json()["detail"]


def test_ac_14_a_failing_pipeline_ends_the_job_failed(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(settings: Any = None) -> FakeVLM:
        raise RuntimeError("VLM server không phản hồi")

    monkeypatch.setattr(vlm_providers, "get_vlm_provider", broken)
    video_id = _upload(client, synthetic_video(tmp_path / "pack.mp4", 4)).json()["video_id"]
    job = client.get(f"/jobs/{client.post(f'/videos/{video_id}/process', json={}).json()['job_id']}").json()
    assert job["status"] == "failed" and "không phản hồi" in job["error"]
    assert client.get("/health").status_code == 200  # the server keeps serving


def test_ac_15_the_lots_are_the_sigma_adapters_and_rca_finds_each(client: TestClient) -> None:
    lots = client.get("/sigma/lots").json()
    expected = CsvSigmaAdapter(Settings(_env_file=None).sigma_csv_dir).list_lots()
    assert [lot["lot_id"] for lot in lots] == [lot.lot_id for lot in expected]
    flagged = {d.lot_id for d in CsvSigmaAdapter(Settings(_env_file=None).sigma_csv_dir).list_defects()}
    assert {lot["lot_id"] for lot in lots if lot["status"] == "NG"} == flagged
    live_sigma = _sigma(Settings(_env_file=None))  # what the live RCA Agent reads
    for lot in lots:
        assert live_sigma.get_lot(lot["lot_id"]).lot_id == lot["lot_id"]
        assert client.post("/rca/investigate", json={"lot_id": lot["lot_id"]}).status_code == 200  # mock mode


def test_ac_15_lots_filter_by_process(client: TestClient) -> None:
    assert client.get("/sigma/lots", params={"process_id": "NOPE"}).json() == []
    assert {lot["process_id"] for lot in client.get("/sigma/lots", params={"process_id": "PACK01"}).json()} == {
        "PACK01"
    }


def test_sigma_lots_need_the_csv_adapter(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    monkeypatch.setattr(sigma_router, "get_settings", lambda: Settings(_env_file=None, sigma_adapter="sigma_api"))
    res = client.get("/sigma/lots")
    assert res.status_code == 503 and "spec 07" in json.dumps(res.json(), ensure_ascii=False)


def test_ac_17_a_job_left_running_by_a_restart_ends_failed(client: TestClient, store: ProfileStore) -> None:
    from mentormind.backend.app.routers import jobs as jobs_router
    from mentormind.core.schemas import JobStatus

    store.create_job("job-vid-before", "video_process")
    store.update_job("job-vid-before", JobStatus.RUNNING, result={"progress": {"done": 3, "total": 40}})
    with sqlite3.connect(store.db_path) as conn:  # created by the previous API process
        conn.execute("UPDATE jobs SET created_at = ? WHERE job_id = ?", ("2000-01-01T00:00:00+00:00", "job-vid-before"))
    store.create_job("job-vid-now", "video_process")
    store.update_job("job-vid-now", JobStatus.RUNNING)
    assert jobs_router.STARTED_AT > "2000-01-01"

    stale = client.get("/jobs/job-vid-before").json()
    assert stale["status"] == "failed" and "khởi động lại" in stale["error"]
    assert stale["result"] == {"progress": {"done": 3, "total": 40}}  # what it got done is kept
    assert client.get("/jobs/job-vid-now").json()["status"] == "running"


def test_ac_18_hand_activity_without_mediapipe_cuts_by_scene(
    client: TestClient, capture: Capture, tmp_path: Path
) -> None:
    def build(method: Method) -> Segmenter:
        if method == "hand_activity":

            def missing() -> Any:
                raise SegmenterUnavailable("thiếu MediaPipe")

            return HandActivitySegmenter(detector=missing)
        return SceneSegmenter(detect=lambda video, threshold: [(0.0, 10.0), (10.0, 20.0)])

    capture.build = build
    video_id = _upload(client, synthetic_video(tmp_path / "pack.mp4", 20)).json()["video_id"]
    job_id = client.post(f"/videos/{video_id}/process", json={"method": "hand_activity"}).json()["job_id"]
    result = client.get(f"/jobs/{job_id}").json()["result"]
    assert (result["method"], result["method_used"], result["segments"]) == ("hand_activity", "scene", 2)
    assert {s["method"] for s in client.get(f"/videos/{video_id}/segments").json()} == {"scene"}


def test_ac_18_speech_is_transcribed_quoted_per_step_and_turned_into_reasons(
    client: TestClient,
    capture: Capture,
    store: ProfileStore,
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_ffmpeg(monkeypatch, audio=True)
    capture.speech = [
        ASRSegment(text="Nhặt cốc lên nhé.", t_start=0.5, t_end=1.5),
        ASRSegment(text="Xếp nghiêng để cốc không bị nứt.", t_start=9.0, t_end=10.5),
    ]
    reason = {"has_reason": True, "purpose_span": "để cốc không bị nứt"}
    monkeypatch.setattr(llm_providers, "get_llm_provider", lambda s=None: FakeLLM([MERGE, reason]))
    stages: list[str] = []
    update_job = store.update_job

    def spy(job_id: str, status: Any, result: Any = None, error: Any = None) -> Any:
        if result and result.get("progress") and (not stages or stages[-1] != result["progress"]["stage"]):
            stages.append(result["progress"]["stage"])
        return update_job(job_id, status, result=result, error=error)

    monkeypatch.setattr(store, "update_job", spy)
    video_id = _upload(client, synthetic_video(tmp_path / "pack.mp4", 20)).json()["video_id"]
    job_id = client.post(f"/videos/{video_id}/process", json={"method": "fixed_window"}).json()["job_id"]
    job = client.get(f"/jobs/{job_id}").json()
    assert job["status"] == "done", job
    result = job["result"]
    assert (result["transcript_lines"], result["steps_with_excerpt"], result["reasons_filled"]) == (2, 2, 1)
    assert stages == ["cut", "transcribe", "describe", "merge", "reasons"]
    profiles = {p["step"]: p for p in client.get("/profiles", params={"process_id": "PACK01"}).json()}
    picking, placing = profiles["Nhặt cốc từ khay"], profiles["Đặt cốc vào thùng carton"]
    assert picking["evidence"]["transcript_excerpt"] == "Nhặt cốc lên nhé."  # each step only its own words
    assert placing["evidence"]["transcript_excerpt"] == "Xếp nghiêng để cốc không bị nứt."
    assert (placing["reason"], placing["reason_source"], placing["status"]) == (
        "Xếp nghiêng để cốc không bị nứt.",  # the expert's sentence holding the span (spec 04 AC-26)
        "expert_verbal",
        "in_review",
    )
    assert (picking["reason"], picking["status"]) == (None, "draft")  # not in its own words: refused
    # Spec 04 AC-27: the self-check audit sits next to the video's describe artefacts.
    audit = settings.work_dir / "vlm" / video_id / "reasons_audit.jsonl"
    decisions = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
    assert [(d["profile_id"], d["decision"]) for d in decisions] == [
        (picking["profile_id"], "rejected_not_verbatim"),
        (placing["profile_id"], "accepted"),
    ]


@pytest.mark.parametrize(("step_times", "span"), [("segment", (8.0, 15.0)), ("model", (8.0, 11.5))])
def test_ac_28_the_video_job_times_steps_by_the_setting(
    client: TestClient,
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    step_times: str,
    span: tuple[float, float],
) -> None:
    """Spec 04 AC-28: KNOWHOW_VLM_STEP_TIMES reaches pass A of the API job."""
    configured = settings.model_copy(update={"vlm_step_times": step_times})
    monkeypatch.setattr(videos_router, "get_settings", lambda: configured)
    video_id = _upload(client, synthetic_video(tmp_path / "pack.mp4", 20)).json()["video_id"]
    job_id = client.post(f"/videos/{video_id}/process", json={"method": "fixed_window"}).json()["job_id"]
    assert client.get(f"/jobs/{job_id}").json()["status"] == "done"
    drafts = client.get("/profiles", params={"process_id": "PACK01"}).json()
    merged = next(p for p in drafts if p["step"] == "Đặt cốc vào thùng carton")
    assert (merged["evidence"]["t_start"], merged["evidence"]["t_end"]) == span


def test_ac_18_without_a_method_the_server_default_is_used(
    client: TestClient, capture: Capture, settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(videos_router, "get_settings", lambda: settings.model_copy(update={"video_method": "scene"}))
    capture.build = lambda method: SceneSegmenter(detect=lambda video, threshold: [(0.0, 10.0), (10.0, 20.0)])
    video_id = _upload(client, synthetic_video(tmp_path / "pack.mp4", 20)).json()["video_id"]
    job_id = client.post(f"/videos/{video_id}/process", json={"method": None}).json()["job_id"]
    result = client.get(f"/jobs/{job_id}").json()["result"]
    assert (result["method"], result["method_used"]) == ("scene", "scene")


@pytest.mark.parametrize("concurrency", [1, 3])
def test_ac_30_the_video_job_runs_its_requests_in_parallel_with_the_same_result(
    client: TestClient,
    capture: Capture,
    store: ProfileStore,
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    concurrency: int,
) -> None:
    """Spec 04 AC-30: KNOWHOW_VLM_CONCURRENCY reaches the API job; progress only goes up; one audit line per step."""
    from tests.processing.vlm.test_concurrency import KeyedVLM

    configured = settings.model_copy(update={"vlm_concurrency": concurrency})
    monkeypatch.setattr(videos_router, "get_settings", lambda: configured)
    vlm = KeyedVLM(default_delay=0.02)
    monkeypatch.setattr(vlm_providers, "get_vlm_provider", lambda s=None: vlm)
    fake_ffmpeg(monkeypatch, audio=True)
    capture.speech = [
        ASRSegment(text="Đặt nghiêng để cốc không bị nứt.", t_start=1.0, t_end=3.0),
        ASRSegment(text="Nhìn kỹ mép cốc trước khi đóng.", t_start=6.0, t_end=8.0),
        ASRSegment(text="Cốc số hai cũng đặt nghiêng.", t_start=11.0, t_end=13.0),
        ASRSegment(text="Kiểm tra lại lần cuối nhé.", t_start=16.0, t_end=18.0),
    ]
    reason = {"has_reason": True, "purpose_span": "để cốc không bị nứt"}
    monkeypatch.setattr(llm_providers, "get_llm_provider", lambda s=None: FakeLLM([MERGE, reason]))
    progress: list[tuple[str, float]] = []
    update_job = store.update_job

    def spy(job_id: str, status: Any, result: Any = None, error: Any = None) -> Any:
        if result and result.get("progress"):
            progress.append((result["progress"]["stage"], result["progress"]["done"]))
        return update_job(job_id, status, result=result, error=error)

    monkeypatch.setattr(store, "update_job", spy)
    video_id = _upload(client, synthetic_video(tmp_path / "pack.mp4", 20)).json()["video_id"]
    job_id = client.post(f"/videos/{video_id}/process", json={"method": "fixed_window"}).json()["job_id"]
    job = client.get(f"/jobs/{job_id}").json()
    assert job["status"] == "done", job
    assert vlm.max_in_flight == concurrency  # 2 segments x 2 runs = 4 calls, 3 at once when allowed
    examined = job["result"]["steps_with_excerpt"]
    for stage, total in (("describe", 4), ("reasons", examined)):
        done = [d for s, d in progress if s == stage]
        assert done == sorted(done) and done[-1] == total, progress  # progress only goes up
    drafts = sorted(
        (p["step"], p["reason"], p["status"]) for p in client.get("/profiles", params={"process_id": "PACK01"}).json()
    )
    assert drafts == [  # the same whether the requests ran one at a time or 3 at once
        ("Kiểm tra cốc số 2", None, "draft"),
        ("Đặt cốc số 1 vào thùng", "Đặt nghiêng để cốc không bị nứt.", "in_review"),
        ("Đặt cốc vào thùng carton", None, "draft"),  # pass C merged "Kiểm tra cốc số 1" + "Đặt cốc số 2 ..."
    ]
    audit = settings.work_dir / "vlm" / video_id / "reasons_audit.jsonl"
    decisions = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
    assert len(decisions) == examined == len({d["profile_id"] for d in decisions})  # one line per step
    assert sorted(d["decision"] for d in decisions) == ["accepted", *["rejected_not_verbatim"] * (examined - 1)]
