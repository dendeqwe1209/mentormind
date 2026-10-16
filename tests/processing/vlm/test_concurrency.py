"""KNOWHOW_VLM_CONCURRENCY (spec 04 §3, AC-30): passes A and B in parallel, same result as one at a time."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from mentormind.core.config import Settings
from mentormind.core.guard import GuardPolicy
from mentormind.core.guard.image import FaceBlurrer
from mentormind.core.providers.errors import ProviderError
from mentormind.core.providers.models import TokenUsage
from mentormind.core.providers.vlm.backends.fake import FakeVLM
from mentormind.core.providers.vlm.models import ImageInput
from mentormind.processing.vlm.frames.sampler import SampledFrames
from mentormind.processing.vlm.passes.describe import describe_segments
from mentormind.processing.vlm.pipeline import DescribePipeline
from tests.processing.vlm.passes.test_describe import fake_sampler, segments, step


class KeyedVLM(FakeVLM):
    """Answers by segment (read from the frame path), so the answer never depends on call order.

    Records how many calls are in flight at once; ``delays`` makes some segments answer slower.
    """

    def __init__(
        self,
        delays: Mapping[str, float] | None = None,
        default_delay: float = 0.02,
        *,
        is_cloud: bool = False,
        failing: str | None = None,
    ) -> None:
        super().__init__(is_cloud=is_cloud)
        self.failing = failing  # this segment's calls fail like a server that keeps answering 503
        self.delays = dict(delays or {})
        self.default_delay = default_delay
        self.in_flight = 0
        self.max_in_flight = 0
        self.order: list[str] = []
        self._lock = threading.Lock()

    def _complete(
        self,
        images: Sequence[ImageInput],
        prompt: str,
        *,
        json_schema: Mapping[str, Any] | None,
        system: str | None,
        temperature: float | None,
        max_tokens: int | None,
    ) -> tuple[str, TokenUsage | None]:
        segment_id = Path(images[0].path).parent.name
        if segment_id == self.failing:
            with self._lock:
                self.order.append(segment_id)
            raise ProviderError("HTTP 503 after the retries")
        with self._lock:
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            time.sleep(self.delays.get(segment_id, self.default_delay))
        finally:
            with self._lock:
                self.in_flight -= 1
                self.order.append(segment_id)
        number = int(segment_id[-3:])
        answer = {"steps": [step(f"Đặt cốc số {number} vào thùng", 0, 4), step(f"Kiểm tra cốc số {number}", 5, 9)]}
        return json.dumps(answer, ensure_ascii=False), TokenUsage(prompt_tokens=10, completion_tokens=5)


def pipeline(vlm: FakeVLM, concurrency: int, sampler: Any = fake_sampler) -> DescribePipeline:
    return DescribePipeline(
        vlm, process_id="PACK01", default_fps=4.0, max_frames=48, sampler=sampler, concurrency=concurrency
    )


def test_ac_30_parallel_passes_give_the_same_drafts_as_one_at_a_time(tmp_path: Path) -> None:
    one = pipeline(KeyedVLM(), 1).run(segments(6), tmp_path / "one")
    several = pipeline(KeyedVLM(), 3).run(segments(6), tmp_path / "several")
    assert [p.model_dump(exclude={"created_at", "updated_at"}) for p in several.profiles] == [
        p.model_dump(exclude={"created_at", "updated_at"}) for p in one.profiles
    ]
    assert several.steps.steps == one.steps.steps
    for name in ("predictions.json", "profiles.json"):
        assert (tmp_path / "several" / name).exists()
    # both pass-A runs kept their raw answers, as one at a time
    assert len(list((tmp_path / "several" / "pass_a").glob("*.json"))) == 6
    assert len(list((tmp_path / "several" / "pass_b" / "pass_a").glob("*.json"))) == 6


def test_ac_30_requests_in_flight_reach_but_never_exceed_the_concurrency(tmp_path: Path) -> None:
    vlm = KeyedVLM(default_delay=0.05)
    pipeline(vlm, 3).run(segments(6), tmp_path / "run")
    assert len(vlm.order) == 12  # passes A and B: one call per segment each
    assert vlm.max_in_flight == 3
    one_at_a_time = KeyedVLM(default_delay=0.01)
    pipeline(one_at_a_time, 1).run(segments(4), tmp_path / "seq")
    assert one_at_a_time.max_in_flight == 1


def test_ac_30_steps_keep_segment_order_when_the_first_segment_answers_last(tmp_path: Path) -> None:
    vlm = KeyedVLM(delays={"VID-TEST-S001": 0.3}, default_delay=0.01)
    with ThreadPoolExecutor(3) as pool:
        result = describe_segments(
            segments(4), vlm, process_id="PACK01", work_dir=tmp_path, default_fps=4.0, max_frames=48,
            sampler=fake_sampler, executor=pool,
        )  # fmt: skip
    assert vlm.order[-1] == "VID-TEST-S001"  # really answered last
    assert [s.segment_id for s in result.steps] == [f"VID-TEST-S00{i}" for i in (1, 1, 2, 2, 3, 3, 4, 4)]
    assert result.calls == 4 and result.prompt_tokens == 40


def test_ac_30_each_segment_is_sampled_once_although_both_runs_overlap(tmp_path: Path) -> None:
    sampled: list[str] = []
    lock = threading.Lock()

    def counting_sampler(segment: Any, destination: Any, **kwargs: Any) -> SampledFrames:
        with lock:
            sampled.append(segment.segment_id)
        time.sleep(0.02)
        return fake_sampler(segment, destination, **kwargs)

    pipeline(KeyedVLM(), 4, sampler=counting_sampler).run(segments(5), tmp_path / "run")
    assert sorted(sampled) == [f"VID-TEST-S00{i}" for i in range(1, 6)]


def test_ac_30_knowhow_vlm_concurrency_defaults_to_one_and_must_be_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KNOWHOW_VLM_CONCURRENCY", raising=False)
    assert Settings(_env_file=None).vlm_concurrency == 1
    monkeypatch.setenv("KNOWHOW_VLM_CONCURRENCY", "4")
    assert Settings(_env_file=None).vlm_concurrency == 4
    monkeypatch.setenv("KNOWHOW_VLM_CONCURRENCY", "0")
    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_ac_30_cloud_frames_are_face_blurred_one_call_at_a_time(tmp_path: Path) -> None:
    """The face detector is not thread-safe: with N calls in flight blurring must still run one at a time."""
    inside = peak = detected = 0
    lock = threading.Lock()

    def detector(image: Any) -> list[tuple[int, int, int, int]]:
        nonlocal inside, peak, detected
        with lock:
            inside += 1
            peak = max(peak, inside)
        time.sleep(0.002)
        with lock:
            inside -= 1
            detected += 1
        return []

    vlm = KeyedVLM(default_delay=0.03, is_cloud=True)
    vlm.guard_policy = GuardPolicy(audit_dir=tmp_path / "audit")
    vlm.face_blurrer = FaceBlurrer(detector)
    pipeline(vlm, 4).run(segments(6), tmp_path / "run")
    assert vlm.max_in_flight == 4  # the requests themselves still overlap
    assert peak == 1 and detected == 12 * 3  # 12 calls x 3 frames, never two detections at once


@pytest.mark.parametrize("concurrency", [1, 2, 4])
def test_ac_30_an_error_stops_the_queued_requests_of_both_runs(tmp_path: Path, concurrency: int) -> None:
    vlm = KeyedVLM(default_delay=0.05, failing="VID-TEST-S002")
    with pytest.raises(ProviderError):
        pipeline(vlm, concurrency).run(segments(20), tmp_path / "run")
    # sequential: segment 1 then the failing segment 2; in parallel at most the requests already in flight
    assert len(vlm.order) <= 2 + 2 * concurrency
