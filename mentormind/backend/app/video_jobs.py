"""Videos whose process job is queued or running in this API process (spec 08 §2 "Xoá dữ liệu").

Jobs are ``BackgroundTasks`` of this one process (spec 08 §2), so an in-process count is exact and
dies with the process like the jobs do. While a video is held, its steps and files cannot be
deleted: the job still saves steps (describe, then each proposed reason) and writes under
``data/work/vlm/<video_id>/``, so a delete in between would be undone by the job.
"""

from __future__ import annotations

import threading
from collections import Counter
from collections.abc import Iterable


class RunningVideos:
    """A thread-safe count of process jobs per ``video_id``."""

    def __init__(self) -> None:
        self._count: Counter[str] = Counter()
        self._lock = threading.Lock()

    def hold(self, video_id: str) -> None:
        with self._lock:
            self._count[video_id] += 1

    def release(self, video_id: str) -> None:
        with self._lock:
            self._count[video_id] -= 1
            if self._count[video_id] <= 0:
                del self._count[video_id]

    def holds(self, video_id: str | None) -> bool:
        with self._lock:
            return video_id is not None and self._count[video_id] > 0

    def among(self, video_ids: Iterable[str | None]) -> list[str]:
        """The held ones of ``video_ids``, sorted, each once."""
        return sorted({v for v in video_ids if v is not None and self.holds(v)})


running_videos = RunningVideos()


def busy_message(video_ids: list[str]) -> str:
    """The 409 detail: which video is still being processed and what to do."""
    return (
        f"Video {', '.join(video_ids)} đang được xử lý (job chưa xong): job vẫn đang lưu bước và tệp của video, "
        "xoá lúc này sẽ bị job ghi lại. Chờ job xong (hoặc lỗi) rồi xoá. Chưa xoá gì."
    )
