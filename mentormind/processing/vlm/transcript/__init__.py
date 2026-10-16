"""The expert's words for each step (spec 04 §3), the input of propose-reasons (§5).

Spec 03 produces them: ``transcript.json`` (``loader``) and ``align_transcript`` (FR-08, used by
``excerpt.align``). Spec 04 hands every aligned line to one step of its segment
(``excerpt.lines_by_step``). Anything missing means no excerpt.
"""

from mentormind.processing.vlm.transcript.excerpt import (
    DEFAULT_LAG_S,
    DEFAULT_LEAD_S,
    SPEC03_MODULE,
    Aligned,
    align,
    excerpt_text,
    lines_by_step,
)
from mentormind.processing.vlm.transcript.loader import load_transcript, transcript_path

__all__ = [
    "DEFAULT_LAG_S",
    "DEFAULT_LEAD_S",
    "SPEC03_MODULE",
    "Aligned",
    "align",
    "excerpt_text",
    "lines_by_step",
    "load_transcript",
    "transcript_path",
]
