"""Optional classical NN score to prioritise (never automatically approve) Human Review."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from mentormind.backend.app.deps import get_profile_store
from mentormind.core.config import get_settings
from mentormind.knowledge_base.store.profile_store import ProfileStore
from mentormind.nn.model import ModelArtifact, ModelUnavailableError, score_vector
from mentormind.qnn.features import FEATURE_NAMES, extract_review_features
from mentormind.qnn.snapshot_store import ReviewRiskDatasetStore

router = APIRouter(prefix="/nn", tags=["nn"])
RiskLevel = Literal["low", "medium", "high", "unavailable"]


class NnStatusResponse(BaseModel):
    enabled: bool
    trained: bool
    backend: str = "classical.python.mlp"
    samples_total: int = 0
    samples_labeled: int = 0
    samples_risky: int = 0
    samples_clean: int = 0
    validation_metrics: dict[str, float] | None = None


class NnRiskResponse(BaseModel):
    profile_id: str
    enabled: bool
    trained: bool
    available: bool
    score: float | None = None
    level: RiskLevel = "unavailable"
    backend: str = "classical.python.mlp"
    features: dict[str, float]
    reason: str | None = None


@router.get("/status", response_model=NnStatusResponse)
def nn_status() -> NnStatusResponse:
    settings = get_settings()
    counts = ReviewRiskDatasetStore(settings.profile_db).counts()
    response = NnStatusResponse(
        enabled=settings.nn_enabled,
        trained=settings.nn_model_path.is_file(),
        samples_total=counts["total"],
        samples_labeled=counts["labeled"],
        samples_risky=counts["risky"],
        samples_clean=counts["clean"],
    )
    if response.trained:
        try:
            artifact = ModelArtifact.load(settings.nn_model_path)
            response.validation_metrics = artifact.validation_metrics
        except ModelUnavailableError:
            response.trained = False
    return response


@router.get("/profiles/{profile_id}/risk", response_model=NnRiskResponse)
def nn_risk(profile_id: str, store: ProfileStore = Depends(get_profile_store)) -> NnRiskResponse:
    settings = get_settings()
    profile = store.get_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"WorkProfile {profile_id} không tồn tại")
    features = extract_review_features(profile)
    response = NnRiskResponse(
        profile_id=profile_id, enabled=settings.nn_enabled,
        trained=settings.nn_model_path.is_file(), available=False, features=features,
    )
    if not settings.nn_enabled:
        response.reason = "Classical NN đang tắt."
        return response
    if not settings.nn_model_path.is_file():
        response.reason = (
            "Chưa có model. Thu thập reviews có nhãn rồi train bằng knowhow nn train."
        )
        return response
    try:
        artifact = ModelArtifact.load(settings.nn_model_path)
        score = score_vector([features[name] for name in FEATURE_NAMES], artifact)
    except (OSError, ValueError, ModelUnavailableError) as exc:
        response.reason = str(exc)
        return response
    response.available = True
    response.score = score
    response.level = ("low" if score < settings.nn_low_threshold
                      else "high" if score >= settings.nn_high_threshold else "medium")
    return response
