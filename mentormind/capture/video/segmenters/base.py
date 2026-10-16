"""What every cutting method shares (spec 03 FR-03): cuts, the method names, the fallback chain."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from mentormind.core.schemas.video import VideoAsset

log = logging.getLogger(__name__)

Method = Literal["hand_activity", "scene", "fixed_window"]
METHODS: tuple[Method, ...] = ("hand_activity", "scene", "fixed_window")
#: FR-03 order: a method whose library or model is missing hands over to the next one.
FALLBACK: dict[Method, Method | None] = {"hand_activity": "scene", "scene": "fixed_window", "fixed_window": None}


@dataclass(frozen=True)
class Cut:
    """A stretch of the video, before post-processing (FR-04) turns cuts into segments."""

    t_start: float
    t_end: float
    #: 0..1 for the frame sampler of spec 04 (FR-02b); None when not measured.
    motion_score: float | None = None

    @property
    def duration(self) -> float:
        return self.t_end - self.t_start


class Segmenter(Protocol):
    @property
    def name(self) -> Method: ...

    def cut(self, video: Path, asset: VideoAsset) -> list[Cut]: ...


class SegmenterUnavailable(RuntimeError):
    """The method cannot serve this video (library or model missing, no hands in view): the next one is used (FR-03)."""


def cut_with_fallback(
    method: Method, video: Path, asset: VideoAsset, *, build: Callable[[Method], Segmenter]
) -> tuple[list[Cut], Method]:
    """Cuts of ``video`` by ``method``, or by the first method after it that can run; and that method.

    A method hands over when it is unavailable or fails while running (AC-12): one unreadable frame
    in PySceneDetect must not stop the video when ``fixed_window`` can still cut it.

    Raises:
        Exception: whatever stopped ``fixed_window``, the end of the chain.
    """
    current: Method = method
    while True:
        try:
            return build(current).cut(video, asset), current
        except Exception as exc:
            following = FALLBACK[current]
            if following is None:
                raise
            log.warning("Không cắt được bằng %s (%s): chuyển sang %s", current, exc, following)
            current = following
