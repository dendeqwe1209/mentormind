"""spec 04 FR-06 — where draft profiles go: spec 08's store by default, a JSON file otherwise."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from mentormind.core.config import Settings
from mentormind.core.schemas import WorkProfile
from mentormind.processing.vlm.profiles import (
    FileProfileSink,
    ProfileSinkError,
    StoreProfileSink,
    get_profile_sink,
)


def profile(n: int, video: str = "VID-A", status: str = "draft") -> WorkProfile:
    data: dict[str, Any] = {
        "schema_version": "1.0",
        "profile_id": f"WP-PACK01-{n:03d}",
        "process_id": "PACK01",
        "step_order": n,
        "step": f"Bước số {n}",
        "actor": "human",
        "evidence": {"video_id": video, "t_start": n, "t_end": n + 1, "segment_ids": []},
        "confidence": 0.8,
        "generated_by": "vlm",
        "data_classification": "public",
        "status": status,
        "created_at": datetime(2026, 9, 28, tzinfo=UTC),
    }
    if status == "approved":
        data["review"] = {"reviewer": "EXP-001", "reviewed_at": datetime(2026, 9, 29, tzinfo=UTC)}
    return WorkProfile.model_validate(data)


class FakeStore:
    """The part of spec 08 ``ProfileStore`` the sink uses (PR #4: save/get/list)."""

    def __init__(self, *profiles: WorkProfile) -> None:
        self.rows = {p.profile_id: p for p in profiles}

    def save_profile(self, profile: WorkProfile) -> WorkProfile:
        self.rows[profile.profile_id] = profile
        return profile

    def get_profile(self, profile_id: str) -> WorkProfile | None:
        return self.rows.get(profile_id)

    def list_profiles(self, process_id: str | None = None, status: str | None = None) -> list[WorkProfile]:
        return [p for p in self.rows.values() if process_id in (None, p.process_id)]


def settings(tmp_path: Path, sink: str) -> Settings:
    return Settings(_env_file=None, profile_sink=sink, profile_db=tmp_path / "p.sqlite")


def test_file_sink_round_trips_one_video(tmp_path: Path) -> None:
    sink = FileProfileSink(tmp_path)
    sink.save("VID-A", [profile(1), profile(2)])
    assert [p.profile_id for p in sink.load("VID-A")] == ["WP-PACK01-001", "WP-PACK01-002"]
    assert (tmp_path / "vlm" / "VID-A" / "profiles.json").is_file()


def test_store_sink_saves_and_loads_by_video(tmp_path: Path) -> None:
    store = FakeStore(profile(7, video="VID-B", status="approved"))
    sink = StoreProfileSink(store)
    saved = sink.save("VID-A", [profile(1), profile(2)])
    assert [p.profile_id for p in saved] == ["WP-PACK01-001", "WP-PACK01-002"]
    assert [p.profile_id for p in sink.load("VID-A")] == ["WP-PACK01-001", "WP-PACK01-002"]


def test_store_sink_never_overwrites_another_videos_profile(tmp_path: Path) -> None:
    approved = profile(1, video="VID-B", status="approved")
    store = FakeStore(approved, profile(2, video="VID-B"))
    saved = StoreProfileSink(store).save("VID-A", [profile(1), profile(2)])
    assert [p.profile_id for p in saved] == ["WP-PACK01-003", "WP-PACK01-004"]
    assert store.rows["WP-PACK01-001"] == approved  # untouched


def test_store_sink_replaces_the_same_videos_drafts_on_a_rerun(tmp_path: Path) -> None:
    store = FakeStore(profile(1), profile(2))
    rerun = [profile(1).model_copy(update={"step": "Bước mới"})]
    saved = StoreProfileSink(store).save("VID-A", rerun)
    assert saved[0].profile_id == "WP-PACK01-001" and store.rows["WP-PACK01-001"].step == "Bước mới"


def test_store_sink_keeps_a_reviewed_profile_of_the_same_video(tmp_path: Path) -> None:
    reviewed = profile(1, status="approved")
    store = FakeStore(reviewed)
    saved = StoreProfileSink(store).save("VID-A", [profile(1)])
    assert saved[0].profile_id == "WP-PACK01-002" and store.rows["WP-PACK01-001"] == reviewed


def test_store_sink_never_overwrites_a_draft_it_just_renumbered(tmp_path: Path) -> None:
    # VID-B's 001 is moved to 002, then VID-B's own 002 must not land on it.
    store = FakeStore(profile(1, video="VID-A", status="approved"))
    saved = StoreProfileSink(store).save("VID-B", [profile(1, "VID-B"), profile(2, "VID-B")])
    assert [p.profile_id for p in saved] == ["WP-PACK01-002", "WP-PACK01-003"]
    assert [store.rows[p.profile_id].step for p in saved] == ["Bước số 1", "Bước số 2"]


def test_auto_falls_back_to_the_file_until_spec08_lands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mentormind.processing.vlm.profiles import sinks

    monkeypatch.setattr(sinks, "_store_class", lambda: None)
    sink = get_profile_sink(settings(tmp_path, "auto"), work_dir=tmp_path)
    assert isinstance(sink, FileProfileSink)


def test_asking_for_the_store_before_it_exists_is_a_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mentormind.processing.vlm.profiles import sinks

    monkeypatch.setattr(sinks, "_store_class", lambda: None)
    with pytest.raises(ProfileSinkError, match="spec 08"):
        get_profile_sink(settings(tmp_path, "store"), work_dir=tmp_path)


def test_auto_uses_the_store_once_it_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mentormind.processing.vlm.profiles import sinks

    monkeypatch.setattr(sinks, "_store_class", lambda: lambda db_path: FakeStore())
    sink = get_profile_sink(settings(tmp_path, "auto"), work_dir=tmp_path)
    assert isinstance(sink, StoreProfileSink)


def test_a_store_that_exists_but_cannot_import_is_reported_not_hidden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib

    from mentormind.processing.vlm.profiles import sinks

    def broken(name: str) -> object:
        raise ImportError("cannot import name 'ErrorTag' from 'mentormind.core.schemas'")

    monkeypatch.setattr(importlib, "import_module", broken)
    with pytest.raises(ProfileSinkError, match="không import được"):
        sinks.get_profile_sink(settings(tmp_path, "auto"), work_dir=tmp_path)
