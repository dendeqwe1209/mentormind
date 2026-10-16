"""Pass B — self-consistency (spec 04 §3, T04-4).

Pass A runs twice on the same segments (``temperature=0.2``). A step survives only when BOTH runs
report it in the same segment: ``token_set_ratio(step) >= 70`` and overlapping times (the matching
rule of :mod:`passes.matching`), paired one-to-one, best score first. Small VLMs "see" plausible
actions that are not in the video; an invented step rarely comes back the same way twice.

The kept step is the first run's, with ``confidence = mean(c1, c2) x score / 100``. Its ``actor`` is
the one both runs saw (one run's if the other could not tell, unknown if they disagree). A segment
that failed in either run is failed: its steps cannot be confirmed.
"""

from __future__ import annotations

from mentormind.core.schemas import Actor
from mentormind.processing.vlm.passes.matching import MATCH_THRESHOLD, overlaps, similarity
from mentormind.processing.vlm.passes.models import PassAResult, TimedStep


def self_consistent(first: PassAResult, second: PassAResult, threshold: float = MATCH_THRESHOLD) -> PassAResult:
    """Steps both runs agree on, plus both runs' failures, scenes and costs (AC-04)."""
    failed = {f.segment_id: f for f in [*first.failed, *second.failed]}
    kept: list[TimedStep] = []
    for segment_id in dict.fromkeys(s.segment_id for s in first.steps):
        if segment_id in failed:
            continue
        ours = [s for s in first.steps if s.segment_id == segment_id]
        theirs = [s for s in second.steps if s.segment_id == segment_id]
        kept += _agreed(ours, theirs, threshold)
    return PassAResult(
        steps=sorted(kept, key=lambda s: (s.t_start, s.t_end)),
        failed=list(failed.values()),
        scenes={**second.scenes, **first.scenes},
        prompt_tokens=first.prompt_tokens + second.prompt_tokens,
        completion_tokens=first.completion_tokens + second.completion_tokens,
        latency_s=first.latency_s + second.latency_s,
        calls=first.calls + second.calls,
    )


def _agreed(ours: list[TimedStep], theirs: list[TimedStep], threshold: float) -> list[TimedStep]:
    """Pairs best score first (ties: model order); the kept steps come back in the first run's order.

    The caller's sort on ``(t_start, t_end)`` is stable, so steps sharing a span (``SegmentTiling``
    gives one span to every step with the same start) keep the order the model returned (§3).
    """
    candidates = sorted(
        (
            (score, i, j)
            for i, a in enumerate(ours)
            for j, b in enumerate(theirs)
            if overlaps(a.t_start, a.t_end, b.t_start, b.t_end) and (score := similarity(a.step, b.step)) >= threshold
        ),
        key=lambda c: (-c[0], c[1], c[2]),
    )
    used_theirs: set[int] = set()
    kept: dict[int, TimedStep] = {}
    for score, i, j in candidates:
        if i in kept or j in used_theirs:
            continue
        used_theirs.add(j)
        confidence = (ours[i].confidence + theirs[j].confidence) / 2 * score / 100
        update = {"confidence": round(confidence, 3), "actor": _actor(ours[i], theirs[j])}
        kept[i] = ours[i].model_copy(update=update)
    return [kept[i] for i in sorted(kept)]


def _actor(a: TimedStep, b: TimedStep) -> Actor | None:
    """The actor both runs saw; one run's when the other could not tell; unknown if they differ."""
    if a.actor is None or b.actor is None:
        return a.actor or b.actor
    return a.actor if a.actor == b.actor else None
