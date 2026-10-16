"""Spec 03 FR-04: cuts become segments of 3–20 s, back to back, covering the whole video.

A cut shorter than 3 s joins the one before it (the first joins the next); a cut longer than 20 s
is split into equal parts of at most 15 s. A video shorter than 3 s is one segment.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from mentormind.capture.video.segmenters.base import Cut

MIN_S = 3.0
MAX_S = 20.0
PART_S = 15.0


def postprocess(cuts: Sequence[Cut], duration: float) -> list[Cut]:
    """FR-04 applied to ``cuts`` of a video of ``duration`` seconds (AC-02, AC-03)."""
    if duration <= 0:
        return []
    merged = _merge_short(_contiguous(cuts, duration))
    return [part for cut in merged for part in _split(cut)]


def _contiguous(cuts: Sequence[Cut], duration: float) -> list[Cut]:
    """Sorted, clipped to the video, each starting where the previous one ends, ending at ``duration``."""
    out: list[Cut] = []
    start = 0.0
    for cut in sorted(cuts, key=lambda c: (c.t_start, c.t_end)):
        end = min(max(cut.t_end, start), duration)
        if end > start:
            out.append(Cut(start, end, cut.motion_score))
            start = end
    if start < duration:
        if out:
            out[-1] = Cut(out[-1].t_start, duration, out[-1].motion_score)
        else:
            out.append(Cut(0.0, duration))
    return out


def _merge_short(cuts: list[Cut]) -> list[Cut]:
    while len(cuts) > 1:
        short = next((i for i, cut in enumerate(cuts) if cut.duration < MIN_S), None)
        if short is None:
            break
        other = short - 1 if short > 0 else 1
        first, second = sorted((short, other))
        cuts[first : second + 1] = [_join(cuts[first], cuts[second])]
    return cuts


def _join(a: Cut, b: Cut) -> Cut:
    scores = [(c.motion_score, c.duration) for c in (a, b) if c.motion_score is not None]
    weight = sum(d for _, d in scores)
    score = round(sum(s * d for s, d in scores) / weight, 3) if scores and weight > 0 else None
    return Cut(a.t_start, b.t_end, score)


def _split(cut: Cut) -> list[Cut]:
    if cut.duration <= MAX_S:
        return [cut]
    parts = math.ceil(cut.duration / PART_S)
    step = cut.duration / parts
    edges = [cut.t_start + i * step for i in range(parts)] + [cut.t_end]
    return [Cut(start, end, cut.motion_score) for start, end in zip(edges, edges[1:], strict=False)]
