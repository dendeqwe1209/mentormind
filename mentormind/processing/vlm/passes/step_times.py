"""Where a pass-A step starts and ends inside its segment (spec 04 §3, AC-24, AC-28).

The VLM answers every step with ``t_start_rel``/``t_end_rel`` (seconds from the segment start). A
:class:`StepTimer` turns them into absolute spans; ``KNOWHOW_VLM_STEP_TIMES`` picks one by name:

    segment  SegmentTiling  (default) the steps tile the segment in start order (AC-24)
    model    ModelSpans     the model's own spans, clamped into the segment (AC-28)

The model points at the instant it sees an action (~1 s spans). On the LASI video, against the
hand-labelled steps, tiling measured better (time recall 0.59 -> 0.85, mean time IoU 0.34 -> 0.50),
hence the default. :func:`get_step_timer` builds one by name, like the provider factories.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from bisect import bisect_right
from collections.abc import Sequence
from typing import ClassVar, Literal

from mentormind.core.schemas.video import Segment
from mentormind.processing.vlm.passes.models import ObservedStep

StepTimerName = Literal["segment", "model"]
#: A step with its absolute ``t_start`` and ``t_end`` (seconds, rounded to 0.01 s).
PlacedStep = tuple[ObservedStep, float, float]


class StepTimer(ABC):
    """Places one segment's steps in time, in the order pass A keeps them."""

    #: Its value of ``KNOWHOW_VLM_STEP_TIMES``.
    name: ClassVar[StepTimerName]

    @abstractmethod
    def place(self, steps: Sequence[ObservedStep], segment: Segment) -> list[PlacedStep]:
        """``(step, t_start, t_end)`` for every step of ``segment``, absolute and inside it."""


class SegmentTiling(StepTimer):
    """The steps, in start order, tile the segment; the model's ``t_end_rel`` is not used (AC-24).

    Each step runs from its own start (the first from the segment start) to the next distinct start
    (the last to the segment end). Starts are clamped to the segment and rounded to 0.01 s. Steps
    sharing a start share one span; a start clamped to the segment end shares the span of the group
    before it, so ``t_end > t_start`` unless the segment itself lasts 0 s.
    """

    name: ClassVar[StepTimerName] = "segment"

    def place(self, steps: Sequence[ObservedStep], segment: Segment) -> list[PlacedStep]:
        seg_start = round(segment.t_start, 2)
        seg_end = round(segment.t_start + max(segment.t_end - segment.t_start, 0.0), 2)
        ordered = sorted(steps, key=lambda s: s.t_start_rel)  # stable: ties keep the model's order
        starts = [min(round(segment.t_start + s.t_start_rel, 2), seg_end) for s in ordered]
        # Span boundaries: the segment start (opened by the first group), then every later distinct start.
        marks = [seg_start, *sorted({t for t in starts[1:] if starts[0] < t < seg_end})]
        tiled = []
        for step, start in zip(ordered, starts, strict=True):
            i = bisect_right(marks, start) - 1
            tiled.append((step, marks[i], marks[i + 1] if i + 1 < len(marks) else seg_end))
        return tiled


class ModelSpans(StepTimer):
    """The model's own ``t_start_rel``-``t_end_rel``, clamped into the segment, in its order (AC-28).

    An end before the start becomes the start; both are cut at the segment end.
    """

    name: ClassVar[StepTimerName] = "model"

    def place(self, steps: Sequence[ObservedStep], segment: Segment) -> list[PlacedStep]:
        duration = max(segment.t_end - segment.t_start, 0.0)
        placed = []
        for step in steps:
            start = min(step.t_start_rel, duration)
            end = min(max(step.t_end_rel, step.t_start_rel), duration)
            placed.append((step, round(segment.t_start + start, 2), round(segment.t_start + end, 2)))
        return placed


STEP_TIMERS: dict[str, type[StepTimer]] = {cls.name: cls for cls in (SegmentTiling, ModelSpans)}
#: What pass A uses when the caller names no timer (``KNOWHOW_VLM_STEP_TIMES`` defaults to it too).
DEFAULT_STEP_TIMER: StepTimer = SegmentTiling()


def get_step_timer(name: str) -> StepTimer:
    """The timer registered as ``name`` (``KNOWHOW_VLM_STEP_TIMES``).

    Raises:
        ValueError: unknown name — never silently falls back to another timer.
    """
    cls = STEP_TIMERS.get(name)
    if cls is None:
        raise ValueError(f"KNOWHOW_VLM_STEP_TIMES '{name}' không có. Các giá trị có sẵn: {', '.join(STEP_TIMERS)}")
    return cls()
