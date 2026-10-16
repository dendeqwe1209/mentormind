"""``align_transcript`` (spec 03 FR-08): which segment each transcript line belongs to.

A line goes to the segment it overlaps most (a tie: the earlier segment); a line outside every
segment goes to the nearest one. Spec 04 then hands each line to one step of that segment (§3).
"""

from __future__ import annotations

from collections.abc import Sequence

from mentormind.core.schemas.video import Segment, TranscriptSegment


def align_transcript(
    segments: Sequence[Segment], transcripts: Sequence[TranscriptSegment]
) -> dict[str, list[TranscriptSegment]]:
    """``segment_id -> its lines`` in time order; every segment has an entry (AC-06)."""
    ordered = sorted(segments, key=lambda s: (s.t_start, s.t_end))
    aligned: dict[str, list[TranscriptSegment]] = {s.segment_id: [] for s in ordered}
    if not ordered:
        return aligned
    for line in sorted(transcripts, key=lambda t: (t.t_start, t.t_end)):
        best = max(ordered, key=lambda s: (_overlap(s, line), -s.t_start))
        if _overlap(best, line) <= 0:
            best = min(ordered, key=lambda s: (_gap(s, line), s.t_start))
        aligned[best.segment_id].append(line)
    return aligned


def _overlap(segment: Segment, line: TranscriptSegment) -> float:
    return min(segment.t_end, line.t_end) - max(segment.t_start, line.t_start)


def _gap(segment: Segment, line: TranscriptSegment) -> float:
    return max(segment.t_start - line.t_end, line.t_start - segment.t_end, 0.0)
