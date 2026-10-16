"""Run pass A once per fps over the same segments and score every run."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from mentormind.core.providers.vlm.base import VLMProvider
from mentormind.core.schemas.video import Segment
from mentormind.processing.vlm.frames.sampler import sample_frames
from mentormind.processing.vlm.passes import describe_segments, to_work_profiles
from mentormind.processing.vlm.passes.describe import Sampler
from mentormind.processing.vlm.passes.step_times import DEFAULT_STEP_TIMER, StepTimer
from mentormind.processing.vlm.sweep.metrics import SweepRow, evaluate
from mentormind.processing.vlm.sweep.truth import TruthStep


def run_sweep(
    segments: Sequence[Segment],
    truth: Sequence[TruthStep],
    fps_values: Sequence[float],
    provider: VLMProvider,
    *,
    process_id: str,
    work_dir: Path,
    max_frames: int,
    sampler: Sampler | None = None,
    step_timer: StepTimer = DEFAULT_STEP_TIMER,
) -> list[SweepRow]:
    """Describe ``segments`` once per fps and score each run. Artefacts go to ``work_dir``.

    ``step_timer``: how pass A places steps in their segment (``KNOWHOW_VLM_STEP_TIMES``), so a
    sweep per value compares them; every row records its name in ``step_times``.
    """
    # The sweep compares sampling rates, so motion-adaptive fps (FR-02b) must not override it.
    fixed = [s.model_copy(update={"motion_score": None}) for s in segments]
    rows = []
    for fps in fps_values:
        run_dir = work_dir / f"fps{fps:g}"
        run_dir.mkdir(parents=True, exist_ok=True)
        result = describe_segments(
            fixed,
            provider,
            process_id=process_id,
            work_dir=run_dir,
            default_fps=fps,
            max_frames=max_frames,
            sampler=sampler or sample_frames,
            step_timer=step_timer,
        )
        (run_dir / "predictions.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
        profiles = to_work_profiles(
            result, segments=fixed, process_id=process_id, provider=provider, model=provider.model
        )
        (run_dir / "profiles_draft.json").write_text(
            json.dumps([p.to_contract_dict() for p in profiles], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        rows.append(
            evaluate(truth, result, fps=fps, provider=provider.name, model=provider.model, step_times=step_timer.name)
        )
    return rows
