"""Read spec 08's SQLite profile store (read-only): profiles and review events."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from mentormind.core.schemas import WorkProfile
from mentormind.core.schemas.evaluation import ReviewEvent


def read_store(db: Path) -> tuple[list[WorkProfile], list[ReviewEvent]]:
    """Profiles and review events of spec 08's store (opened read-only)."""
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        profiles = [
            WorkProfile.model_validate(json.loads(row[0]))
            for row in conn.execute("SELECT data_json FROM profiles ORDER BY profile_id")
        ]
        events = [
            ReviewEvent(
                id=row[0],
                profile_id=row[1],
                action=row[2],
                reviewer=row[3],
                comment=row[4],
                error_tags=_tags(row[5]),
                created_at=row[6],
            )
            for row in conn.execute(
                "SELECT id, profile_id, action, reviewer, comment, error_tags, created_at "
                "FROM review_events ORDER BY id"
            )
        ]
    return profiles, events


def _tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return [t.strip() for t in raw.split(",") if t.strip()]
    return [str(t) for t in value] if isinstance(value, list) else []
