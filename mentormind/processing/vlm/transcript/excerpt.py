"""Each step's ``transcript_excerpt``: the expert's sentences about THAT step (spec 04 §3).

Which segment a line belongs to is spec 03's job (FR-08 ``align_transcript``), imported from
``SPEC03_MODULE``; without it — or without a transcript — there is no alignment and every excerpt
stays ``None``. Spec 04 then hands every line to exactly one step of its segment: the step whose
window ``[t_start - lead, t_end + lag]`` overlaps the line most (an expert explains just before
acting and comments just after), then the one whose own span overlaps it most (a line across two
steps goes to the step it covers more), then the earlier step. A line overlapping no window goes
to the nearest step; a line of a segment without steps is quoted nowhere.
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Mapping, Sequence
from typing import Protocol

from mentormind.core.schemas.video import Segment, TranscriptSegment

log = logging.getLogger(__name__)

#: Module of spec 03 defining ``align_transcript(segments, transcripts)`` (FR-08).
SPEC03_MODULE = "mentormind.capture.video"
#: Seconds before a step's start and after its end that still count as speech about it (spec 04 §3).
DEFAULT_LEAD_S = 2.0
DEFAULT_LAG_S = 3.0

#: segment_id -> the transcript lines spec 03 aligned to it.
Aligned = Mapping[str, Sequence[TranscriptSegment]]


class TimedSpan(Protocol):
    """What a step offers here: its time span and the segments it was observed in."""

    @property
    def t_start(self) -> float: ...

    @property
    def t_end(self) -> float: ...

    def sources(self) -> list[str]: ...


def align(segments: Sequence[Segment], transcript: Sequence[TranscriptSegment]) -> Aligned | None:
    """Spec 03's alignment of ``transcript`` to ``segments``; None without a transcript or spec 03."""
    if not transcript:
        return None
    try:
        align_transcript = importlib.import_module(SPEC03_MODULE).align_transcript
    except (ImportError, AttributeError):
        log.info("No %s.align_transcript (spec 03): transcript_excerpt stays empty", SPEC03_MODULE)
        return None
    aligned: Aligned = align_transcript(segments, transcript)
    return aligned


def lines_by_step(
    steps: Sequence[TimedSpan],
    aligned: Aligned | None,
    *,
    lead_s: float = DEFAULT_LEAD_S,
    lag_s: float = DEFAULT_LAG_S,
) -> list[list[TranscriptSegment]]:
    """The lines each step quotes, in the order of ``steps``; each line goes to one step at most."""
    quoted: list[list[TranscriptSegment]] = [[] for _ in steps]
    if not aligned:
        return quoted
    for segment_id, lines in aligned.items():
        candidates = [i for i, step in enumerate(steps) if segment_id in step.sources()]
        if not candidates:
            continue
        for line in lines:

            def fit(i: int, line: TranscriptSegment = line) -> tuple[float, float, float]:
                step = steps[i]
                window = _overlap(step.t_start - lead_s, step.t_end + lag_s, line)
                return (window, _overlap(step.t_start, step.t_end, line), -step.t_start)

            def distance(i: int, line: TranscriptSegment = line) -> tuple[float, float]:
                return (_gap(steps[i], line), steps[i].t_start)

            best = max(candidates, key=fit)
            if fit(best)[0] <= 0:
                best = min(candidates, key=distance)
            quoted[best].append(line)
    return [sorted(lines, key=lambda t: (t.t_start, t.t_end)) for lines in quoted]


def excerpt_text(lines: Sequence[TranscriptSegment]) -> str | None:
    """The lines joined in time order; None when there is nothing to quote."""
    text = " ".join(line.text.strip() for line in lines if line.text.strip())
    return text or None


def _overlap(start: float, end: float, line: TranscriptSegment) -> float:
    return min(end, line.t_end) - max(start, line.t_start)


def _gap(step: TimedSpan, line: TranscriptSegment) -> float:
    return max(step.t_start - line.t_end, line.t_start - step.t_end, 0.0)
