from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from mentormind.backend.app.deletion import ProfileStoreBusyError, delete_profiles, published
from mentormind.backend.app.deps import LoaderOpener, get_knowledge_loader, get_loader_opener, get_profile_store
from mentormind.backend.app.video_jobs import busy_message, running_videos
from mentormind.core.schemas import (
    ProfileDeleteRequest,
    ProfileDeleteResult,
    ProfileListItem,
    ProfilePatchRequest,
    ReviewAction,
    ReviewRequest,
    WorkProfile,
)
from mentormind.knowledge_base.kg.loader import KnowledgeGraphLoader
from mentormind.knowledge_base.store.profile_store import ProfileStore

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("", response_model=list[ProfileListItem])
def list_profiles(
    process_id: str | None = Query(default=None, description="Mã công đoạn"),
    status: str | None = Query(default=None, description="Trạng thái (draft, in_review, approved, rejected)"),
    store: ProfileStore = Depends(get_profile_store),
) -> list[ProfileListItem]:
    """Each profile with ``published``: whether deleting it also removes it from the graph (spec 08 §2)."""
    actions = store.last_review_actions()
    return [
        ProfileListItem.model_validate(
            {**p.model_dump(mode="json"), "published": published(p, actions.get(p.profile_id))}
        )
        for p in store.list_profiles(process_id=process_id, status=status)
    ]


def _delete(store: ProfileStore, profiles: list[WorkProfile], open_loader: LoaderOpener) -> ProfileDeleteResult:
    """``delete_profiles`` behind the checks every delete route shares (spec 08 §2)."""
    busy = running_videos.among(p.evidence.video_id for p in profiles)
    if busy:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=busy_message(busy))
    try:
        return delete_profiles(store, profiles, open_loader)
    except ProfileStoreBusyError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/delete", response_model=ProfileDeleteResult)
def delete_many(
    req: ProfileDeleteRequest,
    store: ProfileStore = Depends(get_profile_store),
    open_loader: LoaderOpener = Depends(get_loader_opener),
) -> ProfileDeleteResult:
    """Delete several steps (spec 08 §2, AC-21); an approved one that cannot be unloaded is kept."""
    ids = list(dict.fromkeys(req.profile_ids))
    profiles = {pid: store.get_profile(pid) for pid in ids}
    missing = [pid for pid, p in profiles.items() if p is None]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không có bước: {', '.join(missing)}. Chưa xoá bước nào.",
        )
    return _delete(store, [p for p in profiles.values() if p is not None], open_loader)


@router.delete("/{profile_id}", response_model=ProfileDeleteResult)
def delete_one(
    profile_id: str,
    store: ProfileStore = Depends(get_profile_store),
    open_loader: LoaderOpener = Depends(get_loader_opener),
) -> ProfileDeleteResult:
    """Delete one step (spec 08 §2, AC-19, AC-20)."""
    profile = store.get_profile(profile_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"WorkProfile {profile_id} không tồn tại",
        )
    result = _delete(store, [profile], open_loader)
    if result.failed:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Không xoá được bước {profile_id}: {result.failed[0].error}. Bước vẫn được giữ nguyên.",
        )
    return result


@router.get("/{profile_id}")
def get_profile(
    profile_id: str,
    store: ProfileStore = Depends(get_profile_store),
) -> dict[str, Any]:
    res = store.get_profile_with_reviews(profile_id)
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"WorkProfile {profile_id} không tồn tại",
        )
    return res


@router.patch("/{profile_id}", response_model=WorkProfile)
def patch_profile(
    profile_id: str,
    patch_req: ProfilePatchRequest,
    store: ProfileStore = Depends(get_profile_store),
) -> WorkProfile:
    try:
        return store.patch_profile(profile_id, patch_req)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"WorkProfile {profile_id} không tồn tại",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


@router.post("/{profile_id}/review", response_model=WorkProfile)
def review_profile(
    profile_id: str,
    review_req: ReviewRequest,
    store: ProfileStore = Depends(get_profile_store),
    loader: KnowledgeGraphLoader = Depends(get_knowledge_loader),
) -> WorkProfile:
    existing = store.get_profile(profile_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"WorkProfile {profile_id} không tồn tại",
        )

    def publish(profile: WorkProfile) -> None:
        if review_req.action == ReviewAction.APPROVE:
            loader.load_profiles([profile])
        else:
            loader.unload_profile(profile.profile_id)

    def rollback_publish(profile: WorkProfile) -> None:
        # The review is not saved: put the graph back to what the stored profile says.
        if str(getattr(existing.status, "value", existing.status)) == "approved":
            loader.load_profiles([existing])
        elif review_req.action == ReviewAction.APPROVE:
            loader.unload_profile(profile.profile_id)

    try:
        updated = store.record_review(profile_id, review_req, before_save=publish, rollback_publish=rollback_publish)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    return updated
