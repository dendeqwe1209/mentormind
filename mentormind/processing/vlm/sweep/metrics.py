"""Sweep metrics (spec 04 §6): recall, precision, order accuracy, key-point recall."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from mentormind.processing.vlm.passes.models import PassAResult, TimedStep
from mentormind.processing.vlm.sweep.matching import (
    MATCH_THRESHOLD,
    Match,
    match_steps,
    overlaps,
    similarity,
)
from mentormind.processing.vlm.sweep.truth import TruthStep


class SweepRow(BaseModel):
    fps: float
    recall: float
    precision: float
    order_accuracy: float | None
    key_point_recall: float | None
    tokens_used: int
    latency_s: float
    fps_effective: float
    predicted: int
    truth: int
    recall_essential: float | None
    #: Truth steps overlapped in time by ANY prediction — coverage, whatever the wording.
    recall_time_only: float | None
    #: Right actor (human/robot/machine) on the prediction overlapping each truth step the most.
    actor_accuracy: float | None
    failed_segments: int
    provider: str
    model: str
    #: How pass A placed the steps in time (``KNOWHOW_VLM_STEP_TIMES``), so a saved row tells.
    step_times: str


def order_accuracy(matches: Sequence[Match], predicted: Sequence[TimedStep]) -> float | None:
    """(Kendall tau + 1) / 2 over matched pairs: 1.0 = same order as the truth."""
    times = [predicted[m.predicted_index].t_start for m in matches]
    concordant = discordant = 0
    for i in range(len(times)):
        for j in range(i + 1, len(times)):
            if times[j] > times[i]:
                concordant += 1
            elif times[j] < times[i]:
                discordant += 1
    total = concordant + discordant
    return concordant / total if total else None


def key_point_recall(
    truth: Sequence[TruthStep], predicted: Sequence[TimedStep], matches: Sequence[Match]
) -> float | None:
    with_key_point = [i for i, t in enumerate(truth) if t.key_point]
    if not with_key_point:
        return None
    matched = {m.truth_index: predicted[m.predicted_index] for m in matches}
    hits = 0
    for i in with_key_point:
        guess = matched.get(i)
        truth_kp = truth[i].key_point or ""
        if guess and guess.key_point_observed:
            hits += similarity(truth_kp, guess.key_point_observed) >= MATCH_THRESHOLD
    return hits / len(with_key_point)


def actor_accuracy(truth: Sequence[TruthStep], predicted: Sequence[TimedStep]) -> float | None:
    """Share of truth steps whose most-overlapping prediction names the same actor.

    Judged on time, not wording: who does a step is a separate question from how it is phrased.
    Only truth steps with an actor and at least one overlapping prediction with an actor count.
    """
    judged = hits = 0
    for t in truth:
        if t.actor is None:
            continue
        candidates = [p for p in predicted if p.actor and overlaps(t.t_start, t.t_end, p.t_start, p.t_end)]
        if not candidates:
            continue
        best = max(candidates, key=lambda p: min(t.t_end, p.t_end) - max(t.t_start, p.t_start))
        judged += 1
        hits += best.actor == t.actor
    return hits / judged if judged else None


def evaluate(
    truth: Sequence[TruthStep],
    result: PassAResult,
    *,
    fps: float,
    provider: str,
    model: str,
    step_times: str,
) -> SweepRow:
    predicted = result.steps
    matches = match_steps(truth, predicted)
    essential = [i for i, t in enumerate(truth) if t.essential]
    matched_truth = {m.truth_index for m in matches}
    effective = [s.fps for s in predicted] or [fps]
    return SweepRow(
        fps=fps,
        recall=round(len(matches) / len(truth), 3) if truth else 0.0,
        precision=round(len(matches) / len(predicted), 3) if predicted else 0.0,
        order_accuracy=_round(order_accuracy(matches, predicted)),
        key_point_recall=_round(key_point_recall(truth, predicted, matches)),
        tokens_used=result.tokens_used,
        latency_s=round(result.latency_s, 2),
        fps_effective=round(sum(effective) / len(effective), 2),
        predicted=len(predicted),
        truth=len(truth),
        recall_essential=_round(len(matched_truth.intersection(essential)) / len(essential) if essential else None),
        recall_time_only=_round(_time_coverage(truth, predicted)),
        actor_accuracy=_round(actor_accuracy(truth, predicted)),
        failed_segments=len(result.failed),
        provider=provider,
        model=model,
        step_times=step_times,
    )


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 3)


def _time_coverage(truth: Sequence[TruthStep], predicted: Sequence[TimedStep]) -> float | None:
    if not truth:
        return None
    covered = sum(any(overlaps(t.t_start, t.t_end, p.t_start, p.t_end) for p in predicted) for t in truth)
    return covered / len(truth)
