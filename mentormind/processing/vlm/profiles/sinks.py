"""Where draft WorkProfiles go (spec 04 FR-06): spec 08's profile store, or a JSON file.

``KNOWHOW_PROFILE_SINK``:

* ``auto`` (default): the store of spec 08 (``knowledge_base.store.profile_store.ProfileStore``)
  when that module exists, else the file;
* ``store``: the store, an error if it is not there yet;
* ``file``: ``data/work/vlm/<video_id>/profiles.json``.

The store is looked up by module name at run time, so this works before and after spec 08 lands.
Its ``save_profile`` is an upsert keyed by ``profile_id``, and ids are numbered per process, not
per video (``WP-PACK01-001``): a second video would overwrite the first one's profiles. The store
sink therefore only replaces drafts of the SAME video, and moves any other clash to the next free
number of the process, so a reviewed profile is never overwritten by a draft.
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

from mentormind.core.config import Settings
from mentormind.core.schemas import WorkProfile
from mentormind.processing.vlm.pipeline import read_profiles, write_profiles

STORE_MODULE = "mentormind.knowledge_base.store.profile_store"
_NUMBER = re.compile(r"^(WP-[A-Z0-9]+-)(\d{3})$")


class ProfileSinkError(RuntimeError):
    """The requested sink cannot be used."""


class ProfileSink(Protocol):
    #: Where the profiles went, for the CLI message.
    where: str

    def save(self, video_id: str, profiles: Sequence[WorkProfile]) -> list[WorkProfile]:
        """Store the drafts of one video; returns them as stored (ids may be renumbered)."""
        ...

    def load(self, video_id: str) -> list[WorkProfile]: ...


class Store(Protocol):
    """The part of spec 08 ``ProfileStore`` used here."""

    def save_profile(self, profile: WorkProfile) -> WorkProfile: ...

    def get_profile(self, profile_id: str) -> WorkProfile | None: ...

    def list_profiles(self, process_id: str | None = None, status: str | None = None) -> list[WorkProfile]: ...


class FileProfileSink:
    def __init__(self, work_dir: Path) -> None:
        self.work_dir = work_dir
        self.where = str(work_dir / "vlm" / "<video_id>" / "profiles.json")

    def path(self, video_id: str) -> Path:
        return self.work_dir / "vlm" / video_id / "profiles.json"

    def save(self, video_id: str, profiles: Sequence[WorkProfile]) -> list[WorkProfile]:
        write_profiles(profiles, self.path(video_id))
        self.where = str(self.path(video_id))
        return list(profiles)

    def load(self, video_id: str) -> list[WorkProfile]:
        path = self.path(video_id)
        if not path.is_file():
            raise ProfileSinkError(f"Chưa có {path}; chạy `knowhow vlm describe` trước.")
        return read_profiles(path)


class StoreProfileSink:
    def __init__(self, store: Store, where: str = "profile store (spec 08)") -> None:
        self.store = store
        self.where = where

    def save(self, video_id: str, profiles: Sequence[WorkProfile]) -> list[WorkProfile]:
        saved: list[WorkProfile] = []
        # Ids written by THIS call: a draft just saved here is never replaceable, or a renumbered
        # profile would be overwritten by the next one of the same video.
        written: set[str] = set()
        for profile in profiles:
            profile = self._free_id(video_id, profile, written)
            written.add(profile.profile_id)
            saved.append(self.store.save_profile(profile))
        return saved

    def load(self, video_id: str) -> list[WorkProfile]:
        return [p for p in self.store.list_profiles() if p.evidence.video_id == video_id]

    def _free_id(self, video_id: str, profile: WorkProfile, written: set[str]) -> WorkProfile:
        current = self.store.get_profile(profile.profile_id)
        replaceable = (
            current is not None
            and current.evidence.video_id == video_id
            and current.status == "draft"
            and profile.profile_id not in written
        )
        if current is None or replaceable:
            return profile
        match = _NUMBER.match(profile.profile_id)
        if match is None:
            raise ProfileSinkError(f"profile_id {profile.profile_id} không đúng dạng WP-XXX-000.")
        prefix = match.group(1)
        taken = {
            int(m.group(2))
            for p in self.store.list_profiles(process_id=profile.process_id)
            if (m := _NUMBER.match(p.profile_id)) and m.group(1) == prefix
        }
        number = max(taken, default=0) + 1
        if number > 999:
            raise ProfileSinkError(f"Hết số profile_id cho {prefix}.")
        return profile.model_copy(update={"profile_id": f"{prefix}{number:03d}"})


def get_profile_sink(settings: Settings, *, work_dir: Path = Path("data/work")) -> ProfileSink:
    """The sink chosen by ``KNOWHOW_PROFILE_SINK`` (see the module docstring)."""
    if settings.profile_sink == "file":
        return FileProfileSink(work_dir)
    store_class = _store_class()
    if store_class is None:
        if settings.profile_sink == "store":
            raise ProfileSinkError(
                f"Chưa có {STORE_MODULE} (profile store của spec 08, PR #4). Đặt KNOWHOW_PROFILE_SINK=file hoặc auto."
            )
        return FileProfileSink(work_dir)
    store = store_class(db_path=str(settings.profile_db))
    return StoreProfileSink(store, where=f"profile store {settings.profile_db}")


def _store_class() -> Callable[..., Any] | None:
    """``ProfileStore``, or ``None`` when spec 08's module does not exist (yet).

    A module that exists but fails to import is an error, not a reason to fall back to the file:
    silently writing elsewhere would hide the broken store.
    """
    try:
        module = importlib.import_module(STORE_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name and STORE_MODULE.startswith(exc.name):
            return None
        raise ProfileSinkError(f"{STORE_MODULE} có nhưng không import được: {exc}") from exc
    except ImportError as exc:
        raise ProfileSinkError(f"{STORE_MODULE} có nhưng không import được: {exc}") from exc
    store_class: Callable[..., Any] | None = getattr(module, "ProfileStore", None)
    return store_class
