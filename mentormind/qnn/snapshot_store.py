"""SQLite-backed dataset collection for QNN review-risk training."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mentormind.core.schemas import ReviewAction, ReviewRequest, WorkProfile
from mentormind.qnn.features import FEATURE_NAMES, extract_review_features


class ReviewRiskDatasetStore:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        path = Path(self.db_path)
        if path.parent != Path(""):
            path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS qnn_review_samples (
                    profile_id TEXT PRIMARY KEY,
                    features_json TEXT NOT NULL,
                    feature_schema TEXT NOT NULL,
                    snapshot_at TEXT NOT NULL,
                    label INTEGER,
                    review_action TEXT,
                    error_tags_json TEXT,
                    version_before_review INTEGER,
                    reviewed_at TEXT
                )"""
            )

    def ensure_snapshot(self, profile: WorkProfile) -> None:
        now = datetime.now(timezone.utc).isoformat()
        features = extract_review_features(profile)
        with self._connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO qnn_review_samples
                    (profile_id, features_json, feature_schema, snapshot_at, version_before_review)
                   VALUES (?, ?, ?, ?, ?)""",
                (profile.profile_id, json.dumps(features, ensure_ascii=False, sort_keys=True),
                 ",".join(FEATURE_NAMES), now, profile.version),
            )

    def finalize_review(self, profile_before_review: WorkProfile, review: ReviewRequest) -> int:
        self.ensure_snapshot(profile_before_review)
        action = getattr(review.action, "value", review.action)
        tags = [getattr(tag, "value", tag) for tag in review.error_tags]
        risky = action == ReviewAction.REJECT.value or bool(tags) or profile_before_review.version > 1
        label = 1 if risky else 0
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """UPDATE qnn_review_samples
                      SET label = ?, review_action = ?, error_tags_json = ?,
                          version_before_review = ?, reviewed_at = ?
                    WHERE profile_id = ?""",
                (label, str(action), json.dumps(tags, ensure_ascii=False),
                 profile_before_review.version, now, profile_before_review.profile_id),
            )
        return label

    def labeled_samples(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT profile_id, features_json, label, review_action, error_tags_json,
                          version_before_review, snapshot_at, reviewed_at
                     FROM qnn_review_samples
                    WHERE label IS NOT NULL
                    ORDER BY reviewed_at, profile_id"""
            ).fetchall()
        return [{
            "profile_id": row["profile_id"],
            "features": json.loads(row["features_json"]),
            "label": int(row["label"]),
            "review_action": row["review_action"],
            "error_tags": json.loads(row["error_tags_json"] or "[]"),
            "version_before_review": row["version_before_review"],
            "snapshot_at": row["snapshot_at"],
            "reviewed_at": row["reviewed_at"],
        } for row in rows]

    def counts(self) -> dict[str, int]:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT COUNT(*) AS total,
                          SUM(CASE WHEN label IS NOT NULL THEN 1 ELSE 0 END) AS labeled,
                          SUM(CASE WHEN label = 1 THEN 1 ELSE 0 END) AS risky,
                          SUM(CASE WHEN label = 0 THEN 1 ELSE 0 END) AS clean
                     FROM qnn_review_samples"""
            ).fetchone()
        return {
            "total": int(row["total"] or 0),
            "labeled": int(row["labeled"] or 0),
            "risky": int(row["risky"] or 0),
            "clean": int(row["clean"] or 0),
        }
