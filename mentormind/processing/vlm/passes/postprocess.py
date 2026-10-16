"""Mandatory post-processing of pass A into draft WorkProfiles (spec 04 §3).

``reason``/``reason_source`` are forced to None whatever the model said (constitution art. 3,
AC-02), ``status="draft"``, evidence and model_info filled, every profile validated against the
contract before it is returned. ``evidence.transcript_excerpt`` = the expert's sentences about THAT
step (spec 03's transcript and alignment, one step per sentence), the input of propose-reasons (§5).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from mentormind.core.guard import SupportsCloudFlag
from mentormind.core.providers.llm.context import strictest
from mentormind.core.schemas.video import Segment, TranscriptSegment
from mentormind.core.schemas.work_profile import (
    SCHEMA_VERSION,
    WorkProfile,
    validate_against_contract,
)
from mentormind.processing.vlm.passes.models import PassAResult
from mentormind.processing.vlm.transcript import DEFAULT_LAG_S, DEFAULT_LEAD_S, excerpt_text, lines_by_step


def to_work_profiles(
    result: PassAResult,
    *,
    segments: Sequence[Segment],
    process_id: str,
    provider: SupportsCloudFlag,
    model: str,
    aligned_transcript: Mapping[str, Sequence[TranscriptSegment]] | None = None,
    created_at: datetime | None = None,
    transcript_lead_s: float = DEFAULT_LEAD_S,
    transcript_lag_s: float = DEFAULT_LAG_S,
) -> list[WorkProfile]:
    """Post-processing (spec 04 §3): draft profiles in time order, each validated by contract.

    ``aligned_transcript``: the WHOLE video's transcript lines, grouped by segment_id by spec 03's
    ``align_transcript`` (see ``transcript.align``); None = no excerpts. Each line is quoted by one
    step only (``transcript.lines_by_step``, window ``[t_start - lead, t_end + lag]``).
    """
    by_id = {s.segment_id: s for s in segments}
    code = re.sub(r"[^A-Z0-9]", "", process_id.upper()) or "UNKNOWN"
    created = created_at or datetime.now(UTC)
    profiles = []
    ordered = sorted(result.steps, key=lambda s: (s.t_start, s.t_end))
    quoted = lines_by_step(ordered, aligned_transcript, lead_s=transcript_lead_s, lag_s=transcript_lag_s)
    for order, (step, said) in enumerate(zip(ordered, quoted, strict=True), start=1):
        segment = by_id[step.segment_id]
        sources = [by_id[sid] for sid in step.sources()]
        source_ids = [s.segment_id for s in sources]
        profile = WorkProfile(
            schema_version=SCHEMA_VERSION,
            profile_id=f"WP-{code}-{order:03d}",
            process_id=process_id,
            step_order=order,
            step=step.step,
            actor=step.actor,
            hand_action=step.hand_action,
            objects=step.objects,
            key_point=step.key_point_observed,
            # Constitution art. 3: a VLM never supplies the reason, whatever it returned.
            reason=None,
            reason_source=None,
            evidence={
                "video_id": segment.video_id,
                "t_start": step.t_start,
                "t_end": step.t_end,
                "segment_ids": source_ids,
                "keyframes": [kf for s in sources for kf in s.keyframes],
                "transcript_excerpt": excerpt_text(said),
                "document_refs": [],
            },
            confidence=step.confidence,
            generated_by="vlm",
            model_info={"provider": provider.name, "model": model, "fps": step.fps},
            # As sensitive as the strictest segment it comes from and the words it quotes.
            data_classification=strictest(
                [*(s.data_classification for s in sources), *(t.data_classification for t in said)]
            ),
            status="draft",
            created_at=created,
        )
        validate_against_contract(profile)
        profiles.append(profile)
    return profiles
