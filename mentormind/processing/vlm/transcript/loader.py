"""Read a video's transcript as spec 03 writes it: ``<work>/video/<video_id>/transcript.json``.

``knowhow video transcribe`` (spec 03 FR-07/07b) writes a JSON list of ``TranscriptSegment``. No
file (spec 03 not run, silent video) or an unreadable one means no transcript: an empty list and
a log line, never an error that stops ``describe``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from mentormind.core.schemas.video import TranscriptSegment

log = logging.getLogger(__name__)
_LINES = TypeAdapter(list[TranscriptSegment])


def transcript_path(work_dir: Path, video_id: str) -> Path:
    return work_dir / "video" / video_id / "transcript.json"


def load_transcript(work_dir: Path, video_id: str) -> list[TranscriptSegment]:
    """The video's transcript lines; ``[]`` when spec 03 wrote none or the file cannot be used."""
    path = transcript_path(work_dir, video_id)
    if not path.is_file():
        return []
    try:
        lines = _LINES.validate_python(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, ValidationError) as exc:
        log.warning("%s is not a list of TranscriptSegment (spec 03), ignored: %s", path, exc)
        return []
    kept = [line for line in lines if line.video_id == video_id]
    if len(kept) < len(lines):
        log.warning("%s: %d line(s) of another video ignored", path, len(lines) - len(kept))
    return kept
