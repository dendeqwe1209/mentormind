"""Spec 03 (Hoàng) stand-ins: transcript lines and an ``align_transcript`` installed as its module."""

from __future__ import annotations

import types
from collections.abc import Sequence

import pytest

from mentormind.core.schemas.common import DataClassification
from mentormind.core.schemas.video import Segment, TranscriptSegment
from mentormind.processing.vlm.transcript import SPEC03_MODULE


def line(text: str, start: float, end: float, label: str = "synthetic") -> TranscriptSegment:
    return TranscriptSegment(
        video_id="VID-TEST", t_start=start, t_end=end, text=text, language="vi",
        data_classification=DataClassification(label),
    )  # fmt: skip


def _align(segments: Sequence[Segment], lines: Sequence[TranscriptSegment]) -> dict[str, list[TranscriptSegment]]:
    """Spec 03 FR-08 as specified: a line goes to the segment it overlaps most."""
    aligned: dict[str, list[TranscriptSegment]] = {s.segment_id: [] for s in segments}
    for t in lines:
        overlap = {s.segment_id: min(s.t_end, t.t_end) - max(s.t_start, t.t_start) for s in segments}
        best = max(overlap, key=lambda sid: overlap[sid])
        if overlap[best] > 0:
            aligned[best].append(t)
    return aligned


def install_spec03(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend spec 03 has landed: ``SPEC03_MODULE.align_transcript`` exists."""
    monkeypatch.setitem(__import__("sys").modules, SPEC03_MODULE, types.SimpleNamespace(align_transcript=_align))


def remove_spec03(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend spec 03 is not installed: importing ``SPEC03_MODULE`` fails."""
    monkeypatch.setitem(__import__("sys").modules, SPEC03_MODULE, None)
