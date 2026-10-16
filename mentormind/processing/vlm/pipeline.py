"""``DescribePipeline`` — the whole spec 04 §3 pipeline: segments in, draft WorkProfiles out.

    pass A   describe every segment (VLM)                          passes/describe.py
    pass B   pass A a second time; keep steps both runs report     passes/consistency.py
    pass C   merge steps cut by segment boundaries (text LLM)      passes/merge.py
    post     reason=None, status=draft, evidence, contract check   passes/postprocess.py
             + the expert's words from spec 03's transcript         transcript/

Artefacts under ``work_dir`` (FR-06): ``pass_a/`` (run 1 raw answers), ``pass_b/pass_a/`` (run 2),
``pass_c.json``, ``failed_segments.json``, ``predictions.json`` (final steps), ``profiles.json``.
Frames are sampled once per segment and reused by both runs. ``concurrency`` > 1
(``KNOWHOW_VLM_CONCURRENCY``) runs both pass-A runs at once over one pool of that many workers: the
requests in flight never exceed it, and the result is the one of the sequential passes (AC-30).
"""

from __future__ import annotations

import json
import threading
from collections.abc import Sequence
from concurrent.futures import Executor, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from mentormind.core.providers.llm import LLMProvider
from mentormind.core.providers.vlm.base import VLMProvider
from mentormind.core.schemas.video import Segment, TranscriptSegment
from mentormind.core.schemas.work_profile import WorkProfile
from mentormind.processing.vlm.frames.sampler import SampledFrames, sample_frames
from mentormind.processing.vlm.passes import describe_segments, to_work_profiles
from mentormind.processing.vlm.passes.consistency import self_consistent
from mentormind.processing.vlm.passes.describe import Sampler
from mentormind.processing.vlm.passes.merge import MergeReport, merge_steps
from mentormind.processing.vlm.passes.models import PassAResult
from mentormind.processing.vlm.passes.parallel import wait_first_error
from mentormind.processing.vlm.passes.step_times import DEFAULT_STEP_TIMER, StepTimer
from mentormind.processing.vlm.transcript import DEFAULT_LAG_S, DEFAULT_LEAD_S, align


class DescribeResult(BaseModel):
    profiles: list[WorkProfile]
    #: Steps after the last pass that ran (absolute times).
    steps: PassAResult
    #: Steps pass A reported on its first run, before pass B filtered them.
    pass_a_steps: int
    merge: MergeReport | None = None
    failed_segments: list[str]


class DescribePipeline:
    """Segments in, draft WorkProfiles out: passes A, B, C and post-processing (spec 04 §3).

    Configure once, then :meth:`run` any number of videos. Each pass is its own method, so a caller
    (or a test) can run or replace one pass without the others.
    """

    def __init__(
        self,
        vlm: VLMProvider,
        *,
        process_id: str,
        default_fps: float,
        max_frames: int,
        llm: LLMProvider | None = None,
        consistency: bool = True,
        sampler: Sampler = sample_frames,
        transcript_lead_s: float = DEFAULT_LEAD_S,
        transcript_lag_s: float = DEFAULT_LAG_S,
        step_timer: StepTimer = DEFAULT_STEP_TIMER,
        concurrency: int = 1,
    ) -> None:
        self.vlm = vlm
        #: Pass C runs only with an LLM; ``None`` skips it.
        self.llm = llm
        self.process_id = process_id
        self.default_fps = default_fps
        self.max_frames = max_frames
        #: Pass B (a second pass-A run, twice the VLM tokens); False skips it.
        self.consistency = consistency
        self._sampler = sampler
        #: Spec 04 §3: speech this long before/after a step still counts as about it.
        self.transcript_lead_s = transcript_lead_s
        self.transcript_lag_s = transcript_lag_s
        #: Spec 04 §3: how pass A places steps in their segment (``KNOWHOW_VLM_STEP_TIMES``).
        self.step_timer = step_timer
        #: VLM requests in flight (passes A and B together); 1 = one at a time (AC-30).
        self.concurrency = max(1, concurrency)

    def run(
        self,
        segments: Sequence[Segment],
        work_dir: Path,
        transcript: Sequence[TranscriptSegment] = (),
    ) -> DescribeResult:
        """All passes over one video's ``segments``; artefacts go to ``work_dir`` (FR-06).

        ``transcript``: spec 03's lines for the video, aligned by spec 03's ``align_transcript``
        into each profile's ``transcript_excerpt`` (none, or no spec 03 yet: no excerpt).
        """
        work_dir.mkdir(parents=True, exist_ok=True)
        sampler = _cache(self._sampler)  # both pass-A runs see the same frames
        first, second = self._both_runs(segments, work_dir, sampler)
        steps = first
        if second is not None:
            steps = self.pass_b(first, second)
        report = None
        if self.llm is not None:
            steps, report = self.pass_c(steps, segments, work_dir)
        profiles = self.postprocess(steps, segments, transcript)
        self._save(steps, profiles, work_dir)
        return DescribeResult(
            profiles=profiles,
            steps=steps,
            pass_a_steps=len(first.steps),
            merge=report,
            failed_segments=[f.segment_id for f in steps.failed],
        )

    def _both_runs(
        self, segments: Sequence[Segment], work_dir: Path, sampler: Sampler
    ) -> tuple[PassAResult, PassAResult | None]:
        """Pass A, and its second run for pass B; at once over one pool when ``concurrency`` > 1."""
        if self.concurrency == 1:
            first = self.pass_a(segments, work_dir, sampler=sampler)
            second = self.pass_a(segments, work_dir / "pass_b", sampler=sampler) if self.consistency else None
            return first, second
        with ThreadPoolExecutor(self.concurrency, thread_name_prefix="vlm") as pool:
            if not self.consistency:
                return self.pass_a(segments, work_dir, sampler=sampler, executor=pool), None
            # Two waiting threads, one per run; every VLM request goes through ``pool``.
            with ThreadPoolExecutor(2, thread_name_prefix="pass") as runs:
                first_run = runs.submit(self.pass_a, segments, work_dir, sampler=sampler, executor=pool)
                second_run = runs.submit(self.pass_a, segments, work_dir / "pass_b", sampler=sampler, executor=pool)
                try:
                    wait_first_error([first_run, second_run])
                except BaseException:
                    # an error (or Ctrl+C) in one run: the other run's queued requests are not sent
                    pool.shutdown(wait=False, cancel_futures=True)
                    raise
                return first_run.result(), second_run.result()

    def pass_a(
        self,
        segments: Sequence[Segment],
        work_dir: Path,
        *,
        sampler: Sampler | None = None,
        executor: Executor | None = None,
    ) -> PassAResult:
        """Describe every segment once (VLM); in parallel over ``executor`` when given."""
        return describe_segments(
            segments,
            self.vlm,
            process_id=self.process_id,
            work_dir=work_dir,
            default_fps=self.default_fps,
            max_frames=self.max_frames,
            sampler=sampler or self._sampler,
            step_timer=self.step_timer,
            executor=executor,
        )

    def pass_b(self, first: PassAResult, second: PassAResult) -> PassAResult:
        """Keep the steps both pass-A runs report."""
        return self_consistent(first, second)

    def pass_c(
        self, steps: PassAResult, segments: Sequence[Segment], work_dir: Path
    ) -> tuple[PassAResult, MergeReport]:
        """Merge steps cut by segment boundaries (text LLM, reverse-checked)."""
        if self.llm is None:
            raise ValueError("Pass C needs an LLM.")
        return merge_steps(steps, segments, self.llm, process_id=self.process_id, work_dir=work_dir)

    def postprocess(
        self, steps: PassAResult, segments: Sequence[Segment], transcript: Sequence[TranscriptSegment] = ()
    ) -> list[WorkProfile]:
        """reason=None, status=draft, evidence (+ transcript excerpt), model_info, contract check."""
        return to_work_profiles(
            steps,
            segments=segments,
            process_id=self.process_id,
            provider=self.vlm,
            model=self.vlm.model,
            aligned_transcript=align(segments, transcript),
            transcript_lead_s=self.transcript_lead_s,
            transcript_lag_s=self.transcript_lag_s,
        )

    @staticmethod
    def _save(steps: PassAResult, profiles: Sequence[WorkProfile], work_dir: Path) -> None:
        failed = work_dir / "failed_segments.json"
        failed.unlink(missing_ok=True)  # pass A's own file only saw the first run
        if steps.failed:
            failed.write_text(
                json.dumps([f.model_dump() for f in steps.failed], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        (work_dir / "predictions.json").write_text(steps.model_dump_json(indent=2), encoding="utf-8")
        write_profiles(profiles, work_dir / "profiles.json")


def write_profiles(profiles: Sequence[WorkProfile], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([p.to_contract_dict() for p in profiles], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_profiles(path: Path) -> list[WorkProfile]:
    return [WorkProfile.model_validate(p) for p in json.loads(path.read_text(encoding="utf-8"))]


def _cache(sampler: Sampler) -> Sampler:
    """The same frames for both pass-A runs: sample each segment once (also when the runs overlap)."""
    seen: dict[str, SampledFrames] = {}
    lock = threading.Lock()  # one sampling at a time: the two runs never sample one segment twice

    def sample(segment: Segment, destination: Any, **kwargs: Any) -> SampledFrames:
        with lock:
            if segment.segment_id not in seen:
                seen[segment.segment_id] = sampler(segment, destination, **kwargs)
            return seen[segment.segment_id]

    return sample
