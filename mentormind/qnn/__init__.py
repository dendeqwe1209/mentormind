"""Quantum-assisted review-risk prioritisation for WorkProfile drafts.

The module is deliberately optional: MentorMind keeps working without PyTorch QNN runtime. When
``KNOWHOW_QNN_ENABLED=true`` the API collects pre-review feature snapshots automatically. Once a
model is trained, the Human-in-the-Loop UI shows a QNN risk score to help reviewers prioritise
which draft to inspect first.
"""

from mentormind.qnn.features import FEATURE_NAMES, extract_review_features

__all__ = ["FEATURE_NAMES", "extract_review_features"]
