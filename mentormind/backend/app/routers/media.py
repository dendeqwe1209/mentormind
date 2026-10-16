from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from mentormind.core.config import get_settings

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/{relpath:path}")
def get_media(relpath: str) -> FileResponse:
    # AC-04: chặn path traversal, chặn `..`
    if ".." in relpath or relpath.startswith("/") or relpath.startswith("\\"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Đường dẫn không hợp lệ (path traversal detected)",
        )

    settings = get_settings()
    allowed_bases = [
        Path(settings.work_dir).resolve(),
        Path(settings.samples_dir).resolve(),
    ]

    target_path = None
    for base in allowed_bases:
        candidate = (base / relpath).resolve()
        # Verify candidate is actually inside base
        try:
            candidate.relative_to(base)
            if candidate.is_file():
                target_path = candidate
                break
        except ValueError:
            continue

    if not target_path or not target_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File không tồn tại",
        )

    return FileResponse(path=str(target_path))
