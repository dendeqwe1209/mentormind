"""Deleting steps from the UI (spec 08 §2 "Xoá dữ liệu", AC-19..AC-22).

A step that reached the knowledge graph is unloaded first (spec 05 FR-04: its ``Step`` and its
pgvector chunk) and only then removed from the profile store, so the store never forgets a step
the graph still serves. A step that never reached the graph is only removed from the store:
Neo4j and pgvector are not even opened, so deleting drafts works while they are down.

The store's write lock is taken before unloading and held until the delete commits (as
``record_review`` holds it while publishing), so an approve in flight cannot make the store delete
time out after the graph already dropped the step; a store that stays locked is reported as
:class:`ProfileStoreBusyError` with nothing changed.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from typing import Protocol

from mentormind.core.schemas import DeleteFailure, ProfileDeleteResult, WorkProfile
from mentormind.knowledge_base.store.profile_store import ProfileStore


class Unloader(Protocol):
    """The part of ``KnowledgeGraphLoader`` deletion needs."""

    def unload_profile(self, profile_id: str) -> None: ...


UnloaderOpener = Callable[[], AbstractContextManager[Unloader]]

BUSY = "Kho profile đang bận (một thao tác duyệt khác đang ghi), chưa xoá gì; thử lại sau vài giây."


class ProfileStoreBusyError(RuntimeError):
    """The profile store stayed locked by another write: nothing was deleted from it (retrying finishes)."""


def published(profile: WorkProfile, last_review_action: str | None) -> bool:
    """In the graph (spec 08 §2): approved, or edited back to ``in_review`` after an approval.

    An edit keeps the approved version in the graph (AC-01). It is known from the last review event,
    or, for a step that came in approved without one (``seed_demo``, a profile loaded by
    ``kg load-profiles``), from the review block it still carries and no reject since.
    """
    if profile.status == "approved" or last_review_action == "approve":
        return True
    return profile.status == "in_review" and profile.review is not None and last_review_action is None


def is_published(store: ProfileStore, profile: WorkProfile) -> bool:
    return published(profile, store.last_review_action(profile.profile_id))


def delete_profiles(
    store: ProfileStore, profiles: Sequence[WorkProfile], open_loader: UnloaderOpener
) -> ProfileDeleteResult:
    """Delete ``profiles``; a published one whose unloading fails is kept and listed in ``failed``.

    Raises:
        ProfileStoreBusyError: the store stayed locked; the delete was rolled back.
    """
    try:
        with store.deleting() as delete:
            # Under the write lock no review can land in between: decide from what the store holds now.
            current = [store.get_profile(p.profile_id) or p for p in profiles]
            to_unload = [p.profile_id for p in current if is_published(store, p)]
            unloaded, failed = _unload(to_unload, open_loader) if to_unload else ([], [])
            kept = {f.profile_id for f in failed}
            removable = [p.profile_id for p in profiles if p.profile_id not in kept]
            delete(removable)
    except sqlite3.OperationalError as exc:
        raise ProfileStoreBusyError(f"{BUSY} ({exc})") from exc
    return ProfileDeleteResult(deleted=removable, unpublished=unloaded, failed=failed)


def _unload(profile_ids: list[str], open_loader: UnloaderOpener) -> tuple[list[str], list[DeleteFailure]]:
    done: list[str] = []
    errors: dict[str, str] = {}
    try:
        with open_loader() as loader:
            for profile_id in profile_ids:
                try:
                    loader.unload_profile(profile_id)
                except Exception as exc:  # the loader restores what it had touched (spec 05 FR-04)
                    errors[profile_id] = _why(exc)
                else:
                    done.append(profile_id)
    except Exception as exc:  # Neo4j or pgvector unreachable: whatever was not unloaded stays
        for profile_id in profile_ids:
            if profile_id not in done:
                errors.setdefault(profile_id, _why(exc))
    return done, [DeleteFailure(profile_id=p, error=errors[p]) for p in profile_ids if p in errors]


def _why(exc: Exception) -> str:
    return f"chưa gỡ được khỏi đồ thị tri thức / kho vector ({str(exc) or type(exc).__name__})"
