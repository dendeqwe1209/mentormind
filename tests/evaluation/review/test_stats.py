"""spec 09 T09-3 — review-stats and reason_coverage (AC-04, AC-07)."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mentormind.core.schemas import WorkProfile
from mentormind.core.schemas.evaluation import ReviewEvent
from mentormind.evaluation.review import read_store, review_stats

NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def profile(
    n: int,
    *,
    version: int = 1,
    label: str = "synthetic",
    reason: bool = False,
    status: str = "approved",
) -> WorkProfile:
    data: dict[str, Any] = {
        "schema_version": "1.0",
        "profile_id": f"WP-PACK01-{n:03d}",
        "process_id": "PACK01",
        "step_order": n,
        "step": f"Bước số {n}",
        "actor": "human",
        "evidence": {"video_id": "VID-TEST", "t_start": 0, "t_end": 1, "segment_ids": []},
        "confidence": 0.8,
        "generated_by": "vlm",
        "data_classification": label,
        "status": status,
        "created_at": NOW,
        "version": version,
    }
    if status == "approved":
        data["review"] = {"reviewer": "EXP-001", "reviewed_at": NOW}
    if reason:
        data.update(reason="tránh trầy bề mặt", reason_source="expert_verbal")
    return WorkProfile.model_validate(data)


def event(i: int, profile_id: str, action: str, tags: list[str]) -> ReviewEvent:
    return ReviewEvent.model_validate(
        {
            "id": i,
            "profile_id": profile_id,
            "action": action,
            "reviewer": "EXP-001",
            "comment": None if action == "approve" else "sai",
            "error_tags": tags,
            "created_at": NOW,
        }
    )


def ten_events() -> tuple[list[WorkProfile], list[ReviewEvent]]:
    profiles = [
        profile(n, version=2 if n in (5, 6) else 1, status="approved" if n <= 6 else "rejected") for n in range(1, 11)
    ]
    tags = {
        5: ["missed_step"],
        6: ["wrong_order"],
        7: ["missed_step", "hallucinated_step"],
        8: ["hallucinated_step"],
        9: ["missed_step"],
        10: [],
    }
    events = [event(n, f"WP-PACK01-{n:03d}", "approve" if n <= 6 else "reject", tags.get(n, [])) for n in range(1, 11)]
    return profiles, events


def test_ac_04_ten_review_events_give_the_rates_and_the_error_tags() -> None:
    stats = review_stats(*ten_events())
    assert stats.events == 10
    assert (stats.approved_unchanged, stats.approved_after_edit, stats.rejected) == (0.4, 0.2, 0.4)
    assert stats.error_tags == {"missed_step": 3, "hallucinated_step": 2, "wrong_order": 1}


def test_ac_07_reason_coverage_per_label_with_the_synthetic_threshold() -> None:
    profiles = [profile(n, reason=n <= 3) for n in range(1, 6)]
    profiles += [profile(n, label="public") for n in (6, 7)]
    stats = review_stats(profiles, [])
    assert stats.reason_coverage == {"synthetic": 0.6, "public": 0.0}
    assert stats.reason_coverage_ok is True  # 0.6 >= 0.6 on synthetic; public is not compared


def test_the_store_is_read_with_the_spec08_schema(tmp_path: Path) -> None:
    db = tmp_path / "profiles.sqlite"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """CREATE TABLE profiles (profile_id TEXT PRIMARY KEY, process_id TEXT NOT NULL,
               status TEXT NOT NULL, version INTEGER NOT NULL, data_json TEXT NOT NULL,
               updated_at TEXT NOT NULL);
               CREATE TABLE review_events (id INTEGER PRIMARY KEY AUTOINCREMENT,
               profile_id TEXT NOT NULL, action TEXT NOT NULL, reviewer TEXT NOT NULL,
               comment TEXT, error_tags TEXT, created_at TEXT NOT NULL);"""
        )
        p = profile(1, reason=True)
        conn.execute(
            "INSERT INTO profiles VALUES (?,?,?,?,?,?)",
            (
                p.profile_id,
                p.process_id,
                p.status,
                p.version,
                json.dumps(p.to_contract_dict(), ensure_ascii=False),
                NOW.isoformat(),
            ),
        )
        conn.execute(
            "INSERT INTO review_events (profile_id, action, reviewer, comment, error_tags,"
            " created_at) VALUES (?,?,?,?,?,?)",
            (p.profile_id, "approve", "EXP-001", None, '["other"]', NOW.isoformat()),
        )
    profiles, events = read_store(db)
    assert [x.profile_id for x in profiles] == ["WP-PACK01-001"]
    assert events[0].error_tags == ["other"]
