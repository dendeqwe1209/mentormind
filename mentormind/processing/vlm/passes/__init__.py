"""The VLM passes of spec 04 §3: A (describe), B (consistency), C (merge), propose-reasons.

``describe`` runs pass A, ``postprocess`` turns its steps into draft WorkProfiles, ``models`` holds
the data exchanged between them and ``prompting`` renders the ``prompts/*.md`` templates.
"""

from mentormind.processing.vlm.passes.describe import PASS_A_SCHEMA, describe_segments
from mentormind.processing.vlm.passes.models import (
    FailedSegment,
    ObservedStep,
    PassAResult,
    TimedStep,
)
from mentormind.processing.vlm.passes.postprocess import to_work_profiles

__all__ = [
    "PASS_A_SCHEMA",
    "FailedSegment",
    "ObservedStep",
    "PassAResult",
    "TimedStep",
    "describe_segments",
    "to_work_profiles",
]
