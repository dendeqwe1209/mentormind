"""Classical NN training tests; no torch/scikit-learn/runtime network required."""
from __future__ import annotations

import random

import pytest

from mentormind.nn.model import (
    ModelArtifact,
    ModelUnavailableError,
    save_model,
    score_vector,
    train_model,
)
from mentormind.qnn.features import FEATURE_NAMES


def _samples(n: int = 100) -> list[dict]:
    rng = random.Random(21)
    records = []
    for i in range(n):
        features = {name: rng.random() for name in FEATURE_NAMES}
        # Synthetic label to verify MLP learning/serialization, not a claim of real performance.
        label = int(features["vlm_confidence"] < 0.5)
        records.append({"profile_id": f"profile-{i}", "features": features, "label": label})
    return records


def test_train_and_reload_reproducible(tmp_path) -> None:
    samples = _samples()
    a = train_model(samples, epochs=130, seed=7)
    b = train_model(samples, epochs=130, seed=7)
    x = [samples[0]["features"][n] for n in FEATURE_NAMES]
    assert score_vector(x, a) == pytest.approx(score_vector(x, b))
    assert 0 <= score_vector(x, a) <= 1
    assert a.validation_samples > 0
    assert a.validation_metrics["accuracy"] >= 0.5
    saved = save_model(a, tmp_path / "nn.json")
    loaded = ModelArtifact.load(saved)
    assert score_vector(x, a) == pytest.approx(score_vector(x, loaded))


def test_reject_small_imbalanced_or_duplicate_datasets() -> None:
    with pytest.raises(ValueError, match="40"):
        train_model(_samples(20))
    samples = _samples()
    for row in samples:
        row["label"] = 1
    with pytest.raises(ValueError, match="10"):
        train_model(samples)
    samples = _samples()
    samples[1]["profile_id"] = samples[0]["profile_id"]
    with pytest.raises(ValueError, match="nhiều lần"):
        train_model(samples)


def test_fail_closed_for_invalid_model_and_vector(tmp_path) -> None:
    model = train_model(_samples(), epochs=3)
    with pytest.raises(ModelUnavailableError):
        score_vector([float("nan")] * len(FEATURE_NAMES), model)
    path = save_model(model, tmp_path / "model.json")
    path.write_text(path.read_text().replace("vlm_confidence", "incorrect_feature"))
    with pytest.raises(ModelUnavailableError):
        ModelArtifact.load(path)
