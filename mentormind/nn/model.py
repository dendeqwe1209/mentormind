"""Small CPU-only ReLU MLP for prioritising human review.

This produces a research/prototype prioritisation score, not a calibrated risk
probability or a robustness certificate. No external numerical dependencies.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mentormind.qnn.features import FEATURE_NAMES

SCHEMA_VERSION = "1.0"
MODEL_TYPE = "classical_review_risk_mlp"


class ModelUnavailableError(ValueError):
    """An artifact is missing or incompatible with the feature contract."""


def _features(values: dict[str, Any]) -> list[float]:
    if set(values) != set(FEATURE_NAMES):
        raise ModelUnavailableError("Feature schema không khớp; cần train lại NN.")
    out = [float(values[name]) for name in FEATURE_NAMES]
    if any(not math.isfinite(v) or v < 0 or v > 1 for v in out):
        raise ModelUnavailableError("NN yêu cầu feature hữu hạn trong [0,1].")
    return out


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z)) if z >= 0 else math.exp(z) / (1.0 + math.exp(z))


def _bce(logit: float, target: int) -> float:
    return max(logit, 0.0) - logit * target + math.log1p(math.exp(-abs(logit)))


@dataclass
class ModelArtifact:
    hidden_weights: list[list[float]]
    hidden_bias: list[float]
    output_weights: list[float]
    output_bias: float
    trained_at: str
    training_samples: int
    validation_samples: int
    risky_samples: int
    clean_samples: int
    seed: int
    validation_metrics: dict[str, float]

    def validate(self) -> None:
        size = len(FEATURE_NAMES)
        hidden = len(self.hidden_bias)
        if hidden < 1 or len(self.hidden_weights) != hidden or len(self.output_weights) != hidden:
            raise ModelUnavailableError("Kích thước hidden layer không hợp lệ.")
        weights = [self.output_bias, *self.hidden_bias, *self.output_weights]
        for row in self.hidden_weights:
            if len(row) != size:
                raise ModelUnavailableError("Feature dimension không khớp NN artifact.")
            weights.extend(row)
        if any(not math.isfinite(float(x)) for x in weights):
            raise ModelUnavailableError("NN artifact chứa tham số không hữu hạn.")

    @classmethod
    def load(cls, path: str | Path) -> "ModelArtifact":
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if data.get("schema_version") != SCHEMA_VERSION or data.get("model_type") != MODEL_TYPE:
                raise ModelUnavailableError("NN artifact sai schema hoặc model type.")
            if tuple(data.get("feature_names", [])) != FEATURE_NAMES:
                raise ModelUnavailableError("NN artifact không khớp feature schema hiện tại.")
            artifact = cls(
                hidden_weights=data["hidden_weights"], hidden_bias=data["hidden_bias"],
                output_weights=data["output_weights"], output_bias=float(data["output_bias"]),
                trained_at=str(data["trained_at"]), training_samples=int(data["training_samples"]),
                validation_samples=int(data["validation_samples"]),
                risky_samples=int(data["risky_samples"]), clean_samples=int(data["clean_samples"]),
                seed=int(data["seed"]), validation_metrics=data["validation_metrics"],
            )
            artifact.validate()
            return artifact
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ModelUnavailableError("Không thể đọc NN model artifact.") from exc


def _forward(x: list[float], model: ModelArtifact) -> tuple[list[float], list[float], float]:
    pre = [sum(w * v for w, v in zip(row, x, strict=True)) + b
           for row, b in zip(model.hidden_weights, model.hidden_bias, strict=True)]
    hidden = [max(0.0, v) for v in pre]
    logit = sum(w * h for w, h in zip(model.output_weights, hidden, strict=True)) + model.output_bias
    return pre, hidden, logit


def score_vector(features: list[float], model: ModelArtifact) -> float:
    if len(features) != len(FEATURE_NAMES) or any(
        not math.isfinite(float(x)) or float(x) < 0 or float(x) > 1 for x in features
    ):
        raise ModelUnavailableError("Feature vector không hợp lệ.")
    model.validate()
    return _sigmoid(_forward(features, model)[2])


def _validation_metrics(data: list[tuple[list[float], int]], model: ModelArtifact) -> dict[str, float]:
    tp = fp = fn = tn = 0
    loss = 0.0
    for x, y in data:
        logit = _forward(x, model)[2]
        loss += _bce(logit, y)
        predicted = _sigmoid(logit) >= 0.5
        if predicted and y: tp += 1
        elif predicted: fp += 1
        elif y: fn += 1
        else: tn += 1
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    return {
        "bce": loss / len(data),
        "accuracy": (tp + tn) / len(data),
        "precision": precision,
        "recall": recall,
        "f1": (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0,
    }


def train_model(
    samples: list[dict[str, Any]], *, hidden_units: int = 12,
    epochs: int = 240, learning_rate: float = 0.025, seed: int = 42,
) -> ModelArtifact:
    """Deterministic stratified holdout and class-balanced SGD with early stopping.

    A minimum dataset size is a training guard, NOT evidence of model quality.
    """
    if not 1 <= hidden_units <= 64 or epochs < 1 or not 0 < learning_rate <= 1:
        raise ValueError("Thông số huấn luyện NN không hợp lệ.")
    if len(samples) < 40:
        raise ValueError("Cần tối thiểu 40 labeled reviews để train NN; hiện chưa đủ.")
    by_class: dict[int, list[tuple[list[float], int]]] = {0: [], 1: []}
    seen: set[str] = set()
    for row in samples:
        identity = str(row["profile_id"])
        if identity in seen:
            raise ValueError("Một profile xuất hiện nhiều lần trong dataset.")
        seen.add(identity)
        y = int(row["label"])
        if y not in by_class:
            raise ValueError("Label phải là 0 hoặc 1.")
        by_class[y].append((_features(row["features"]), y))
    if min(len(part) for part in by_class.values()) < 10:
        raise ValueError("Cần ít nhất 10 mẫu mỗi lớp (clean/risky) để tách validation.")
    rng = random.Random(seed)
    train: list[tuple[list[float], int]] = []
    valid: list[tuple[list[float], int]] = []
    for items in by_class.values():
        rng.shuffle(items)
        n_valid = max(2, round(len(items) * 0.2))
        valid.extend(items[:n_valid])
        train.extend(items[n_valid:])
    counts = {label: sum(1 for _, y in train if y == label) for label in (0, 1)}
    weights = {label: len(train) / (2 * counts[label]) for label in (0, 1)}
    dim = len(FEATURE_NAMES)
    scale = math.sqrt(6.0 / (dim + hidden_units))
    model = ModelArtifact(
        hidden_weights=[[rng.uniform(-scale, scale) for _ in range(dim)] for _ in range(hidden_units)],
        hidden_bias=[0.05] * hidden_units,
        output_weights=[rng.uniform(-scale, scale) for _ in range(hidden_units)],
        output_bias=0.0,
        trained_at="", training_samples=len(train), validation_samples=len(valid),
        risky_samples=len(by_class[1]), clean_samples=len(by_class[0]),
        seed=seed, validation_metrics={},
    )
    best: ModelArtifact | None = None
    best_loss = float("inf")
    stalled = 0
    import copy

    for _ in range(epochs):
        rng.shuffle(train)
        for x, y in train:
            pre, hidden, logit = _forward(x, model)
            delta = (_sigmoid(logit) - y) * weights[y]
            old_output = model.output_weights[:]
            hidden_delta = [delta * old_output[j] if pre[j] > 0 else 0.0
                            for j in range(hidden_units)]
            for j in range(hidden_units):
                model.output_weights[j] -= learning_rate * (
                    delta * hidden[j] + 0.0005 * model.output_weights[j]
                )
            model.output_bias -= learning_rate * delta
            for j in range(hidden_units):
                for k in range(dim):
                    w = model.hidden_weights[j][k]
                    model.hidden_weights[j][k] -= learning_rate * (
                        hidden_delta[j] * x[k] + 0.0005 * w
                    )
                model.hidden_bias[j] -= learning_rate * hidden_delta[j]
        current_loss = _validation_metrics(valid, model)["bce"]
        if current_loss < best_loss - 1e-5:
            best_loss = current_loss
            best = copy.deepcopy(model)
            stalled = 0
        else:
            stalled += 1
            if stalled >= 35:
                break
    assert best is not None
    best.validation_metrics = _validation_metrics(valid, best)
    best.trained_at = datetime.now(timezone.utc).isoformat()
    best.validate()
    return best


def save_model(model: ModelArtifact, path: str | Path) -> Path:
    model.validate()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": SCHEMA_VERSION, "model_type": MODEL_TYPE,
        "feature_names": list(FEATURE_NAMES),
        **vars(model),
    }
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(target)
    return target
