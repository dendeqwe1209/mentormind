"""Stable pre-review features used by the QNN review-risk model.

Only signals available from the AI/video pipeline are used. Human-entered fields (reason,
pass_criteria, review tags, comments...) are intentionally excluded to avoid obvious label leakage.
All features are clipped to [0, 1] so they can be angle-encoded directly on a small circuit.
"""

from __future__ import annotations

from math import isfinite

from mentormind.core.schemas import WorkProfile

FEATURE_NAMES: tuple[str, ...] = (
    "vlm_confidence",
    "segment_duration",
    "keyframe_count",
    "segment_count",
    "transcript_present",
    "transcript_length",
    "actor_known",
    "keyframe_density",
)


def _clip01(value: float) -> float:
    if not isfinite(value):
        return 0.0
    return max(0.0, min(1.0, float(value)))


def extract_review_features(profile: WorkProfile) -> dict[str, float]:
    evidence = profile.evidence
    start = evidence.t_start or 0.0
    end = evidence.t_end if evidence.t_end is not None else start
    duration_s = max(0.0, end - start)
    keyframes = len(evidence.keyframes)
    segments = len(evidence.segment_ids)
    transcript = (evidence.transcript_excerpt or "").strip()
    duration_norm = _clip01(duration_s / 30.0)
    keyframe_norm = _clip01(keyframes / 9.0)
    segment_norm = _clip01(segments / 4.0)
    transcript_len_norm = _clip01(len(transcript) / 600.0)
    density = keyframes / max(duration_s, 1.0)

    return {
        "vlm_confidence": _clip01(profile.confidence),
        "segment_duration": duration_norm,
        "keyframe_count": keyframe_norm,
        "segment_count": segment_norm,
        "transcript_present": 1.0 if transcript else 0.0,
        "transcript_length": transcript_len_norm,
        "actor_known": 1.0 if profile.actor is not None else 0.0,
        "keyframe_density": _clip01(density),
    }


def feature_vector(profile: WorkProfile) -> list[float]:
    features = extract_review_features(profile)
    return [features[name] for name in FEATURE_NAMES]
