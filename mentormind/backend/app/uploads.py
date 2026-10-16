"""Shared checks for uploaded files (spec 08 §2)."""

from pathlib import Path

from fastapi import HTTPException, status


def upload_name(filename: str | None) -> str:
    """The base name of an uploaded file; directory parts (``../``, ``/``, ``\\``) are dropped (AC-10)."""
    name = Path((filename or "").replace("\\", "/")).name
    if name in ("", ".", ".."):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Tên tệp không hợp lệ: {filename!r}.",
        )
    return name
