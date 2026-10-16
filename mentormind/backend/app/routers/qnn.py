"""Quantum-assisted risk scoring for Human-in-the-Loop review prioritisation."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from mentormind.backend.app.deps import get_profile_store
from mentormind.core.config import get_settings
from mentormind.knowledge_base.store.profile_store import ProfileStore
from mentormind.qnn.features import FEATURE_NAMES, extract_review_features, feature_vector
from mentormind.qnn.model import ModelArtifact, QnnUnavailableError, score_vector
from mentormind.qnn.snapshot_store import ReviewRiskDatasetStore

router = APIRouter(prefix="/qnn", tags=["qnn"])
RiskLevel = Literal["low", "medium", "high", "unavailable"]


class QnnStatusResponse(BaseModel):
    enabled: bool
    trained: bool
    backend: str = "torch.statevector"
    n_qubits: int = len(FEATURE_NAMES)
    samples_total: int = 0
    samples_labeled: int = 0
    samples_risky: int = 0
    samples_clean: int = 0
    model_path: str


class QnnRiskResponse(BaseModel):
    profile_id: str
    enabled: bool
    trained: bool
    available: bool
    score: float | None = None
    level: RiskLevel = "unavailable"
    backend: str = "torch.statevector"
    n_qubits: int = len(FEATURE_NAMES)
    features: dict[str, float]
    reason: str | None = None


def _level(score: float, low: float, high: float) -> Literal["low", "medium", "high"]:
    if score < low:
        return "low"
    if score >= high:
        return "high"
    return "medium"


@router.get("/status", response_model=QnnStatusResponse)
def qnn_status() -> QnnStatusResponse:
    settings = get_settings()
    counts = ReviewRiskDatasetStore(settings.profile_db).counts()
    return QnnStatusResponse(
        enabled=settings.qnn_enabled,
        trained=settings.qnn_model_path.is_file(),
        samples_total=counts["total"],
        samples_labeled=counts["labeled"],
        samples_risky=counts["risky"],
        samples_clean=counts["clean"],
        model_path=str(settings.qnn_model_path),
    )


@router.get("/profiles/{profile_id}/risk", response_model=QnnRiskResponse)
def profile_risk(profile_id: str, store: ProfileStore = Depends(get_profile_store)) -> QnnRiskResponse:
    settings = get_settings()
    profile = store.get_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"WorkProfile {profile_id} không tồn tại")
    features = extract_review_features(profile)
    response = QnnRiskResponse(
        profile_id=profile_id,
        enabled=settings.qnn_enabled,
        trained=settings.qnn_model_path.is_file(),
        available=False,
        features=features,
    )
    if not settings.qnn_enabled:
        response.reason = "QNN review-risk đang tắt (KNOWHOW_QNN_ENABLED=false)."
        return response
    if profile.status in {"draft", "in_review"}:
        ReviewRiskDatasetStore(settings.profile_db).ensure_snapshot(profile)
    if not settings.qnn_model_path.is_file():
        response.reason = "Chưa có model đã train. Hệ thống đang thu thập review labels."
        return response
    try:
        artifact = ModelArtifact.load(settings.qnn_model_path)
        score = score_vector(feature_vector(profile), artifact)
    except (OSError, ValueError, QnnUnavailableError) as exc:
        response.reason = str(exc)
        return response
    response.available = True
    response.score = score
    response.level = _level(score, settings.qnn_low_threshold, settings.qnn_high_threshold)
    return response
