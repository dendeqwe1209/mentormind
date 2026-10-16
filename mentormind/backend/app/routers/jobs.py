from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from mentormind.backend.app.deps import get_profile_store
from mentormind.core.schemas import JobResponse, JobStatus
from mentormind.knowledge_base.store.profile_store import ProfileStore

router = APIRouter(prefix="/jobs", tags=["jobs"])

# Jobs are BackgroundTasks of this process (spec 08 §2): one still queued or running from before it
# started died with the previous process and will never finish (AC-17).
STARTED_AT = datetime.now(timezone.utc).isoformat()
RESTARTED = "Máy chủ API đã khởi động lại khi job đang chạy nên job bị dừng giữa chừng; hãy chạy lại."


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    store: ProfileStore = Depends(get_profile_store),
) -> JobResponse:
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} không tồn tại",
        )
    if job.status in (JobStatus.QUEUED, JobStatus.RUNNING) and (job.created_at or "") < STARTED_AT:
        job = store.update_job(job_id, JobStatus.FAILED, result=job.result, error=RESTARTED) or job
    return job
