"""When are two step descriptions "the same step" — the pass-B rule of spec 04 §3.

Two steps match when ``rapidfuzz.token_set_ratio(step) >= 70`` AND their time spans overlap. Pass B
(self-consistency), pass C (reverse check of merged steps) and the sweep scoring all use it.
"""

from __future__ import annotations

from rapidfuzz import fuzz, utils

MATCH_THRESHOLD = 70.0


def similarity(a: str, b: str) -> float:
    return float(fuzz.token_set_ratio(a, b, processor=utils.default_process))


def overlaps(a_start: float, a_end: float, b_start: float, b_end: float) -> bool:
    """Positive overlap; an instantaneous step counts when it falls inside the other interval."""
    if a_end - a_start <= 0:
        return b_start <= a_start <= b_end
    if b_end - b_start <= 0:
        return a_start <= b_start <= a_end
    return min(a_end, b_end) - max(a_start, b_start) > 0
