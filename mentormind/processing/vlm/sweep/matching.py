"""Pairing predicted steps with truth steps — the pass-B rule of spec 04 §3.

A pair needs ``rapidfuzz.token_set_ratio(step) >= 70`` AND a time overlap > 0; each truth step
takes at most one prediction, best score first.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from mentormind.processing.vlm.passes.matching import MATCH_THRESHOLD, overlaps, similarity
from mentormind.processing.vlm.passes.models import TimedStep
from mentormind.processing.vlm.sweep.truth import TruthStep

__all__ = ["MATCH_THRESHOLD", "Match", "match_steps", "overlaps", "similarity"]


class Match(BaseModel):
    truth_index: int
    predicted_index: int
    score: float


def match_steps(
    truth: Sequence[TruthStep],
    predicted: Sequence[TimedStep],
    threshold: float = MATCH_THRESHOLD,
) -> list[Match]:
    candidates = [
        Match(truth_index=ti, predicted_index=pi, score=score)
        for ti, t in enumerate(truth)
        for pi, p in enumerate(predicted)
        if overlaps(t.t_start, t.t_end, p.t_start, p.t_end) and (score := similarity(t.step, p.step)) >= threshold
    ]
    used_truth: set[int] = set()
    used_pred: set[int] = set()
    matches = []
    for candidate in sorted(candidates, key=lambda m: -m.score):
        if candidate.truth_index in used_truth or candidate.predicted_index in used_pred:
            continue
        used_truth.add(candidate.truth_index)
        used_pred.add(candidate.predicted_index)
        matches.append(candidate)
    return sorted(matches, key=lambda m: m.truth_index)
