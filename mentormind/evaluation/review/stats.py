"""``knowhow eval review-stats`` (spec 09 §3A, FR-03; T09-3): what the experts did with the drafts.

* approve without edits / approve after edits / reject, as shares of all review events. "After
  edits" = the profile's ``version`` is above 1 (spec 08: every edit bumps it).
* ``error_tags`` counted over all events.
* ``reason_coverage`` per ``data_classification``: approved profiles that carry a reason. Only
  ``synthetic`` is compared with the MVP threshold (public videos have no expert talking).

"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from pydantic import BaseModel

from mentormind.core.schemas import WorkProfile
from mentormind.core.schemas.evaluation import ReviewEvent

REASON_COVERAGE_THRESHOLD = 0.6  # synthetic videos, spec 09 §3A


class ReviewStats(BaseModel):
    events: int
    approved_unchanged: float | None
    approved_after_edit: float | None
    rejected: float | None
    error_tags: dict[str, int]
    reason_coverage: dict[str, float]
    reason_coverage_threshold: float = REASON_COVERAGE_THRESHOLD
    #: Synthetic coverage against the threshold; None when there is no approved synthetic profile.
    reason_coverage_ok: bool | None


def review_stats(profiles: Sequence[WorkProfile], events: Sequence[ReviewEvent]) -> ReviewStats:
    version = {p.profile_id: p.version for p in profiles}
    approvals = [e for e in events if e.action == "approve"]
    edited = sum(version.get(e.profile_id, 1) > 1 for e in approvals)
    total = len(events)
    tags = Counter(tag for e in events for tag in e.error_tags)
    coverage: dict[str, float] = {}
    for label in dict.fromkeys(str(p.data_classification) for p in profiles if p.status == "approved"):
        approved = [p for p in profiles if p.status == "approved" and p.data_classification == label]
        coverage[label] = round(sum(p.reason is not None for p in approved) / len(approved), 3)
    synthetic = coverage.get("synthetic")
    return ReviewStats(
        events=total,
        approved_unchanged=_share(len(approvals) - edited, total),
        approved_after_edit=_share(edited, total),
        rejected=_share(sum(e.action == "reject" for e in events), total),
        error_tags=dict(tags.most_common()),
        reason_coverage=coverage,
        reason_coverage_ok=None if synthetic is None else synthetic >= REASON_COVERAGE_THRESHOLD,
    )


def _share(count: int, total: int) -> float | None:
    return round(count / total, 3) if total else None
