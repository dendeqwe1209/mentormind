"""Differentiable variational QNN for review-risk scoring.

The MVP uses a tiny 8-qubit state-vector simulator implemented with PyTorch tensor operations.
It preserves real circuit semantics (RY/RZ rotations, CNOT entanglement and Pauli-Z expectations)
without claiming quantum advantage.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mentormind.qnn.features import FEATURE_NAMES

MODEL_SCHEMA_VERSION = "1.0"
MODEL_TYPE = "variational_review_risk_qnn"
BACKEND_NAME = "torch.statevector"


class QnnUnavailableError(RuntimeError):
    pass


def _torch() -> Any:
    try:
        import torch
    except ImportError as exc:
        raise QnnUnavailableError("Thiếu PyTorch cho QNN runtime.") from exc
    return torch


@dataclass(frozen=True)
class ModelArtifact:
    n_qubits: int
    n_layers: int
    theta: list[list[list[float]]]
    readout: list[float]
    bias: float
    trained_at: str
    samples: int
    risky_samples: int
    clean_samples: int
    seed: int

    @classmethod
    def load(cls, path: str | Path) -> "ModelArtifact":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("schema_version") != MODEL_SCHEMA_VERSION or data.get("model_type") != MODEL_TYPE:
            raise QnnUnavailableError(f"QNN model artifact không đúng schema/type: {path}")
        if tuple(data.get("feature_names", [])) != FEATURE_NAMES:
            raise QnnUnavailableError("QNN feature schema không khớp source hiện tại; cần train lại model.")
        return cls(
            n_qubits=int(data["n_qubits"]),
            n_layers=int(data["n_layers"]),
            theta=data["theta"],
            readout=data["readout"],
            bias=float(data["bias"]),
            trained_at=str(data["trained_at"]),
            samples=int(data["samples"]),
            risky_samples=int(data["risky_samples"]),
            clean_samples=int(data["clean_samples"]),
            seed=int(data.get("seed", 42)),
        )


def _ry(theta: Any, torch: Any) -> Any:
    c = torch.cos(theta / 2)
    s = torch.sin(theta / 2)
    return torch.stack((torch.stack((c, -s)), torch.stack((s, c)))).to(torch.complex128)


def _rz(theta: Any, torch: Any) -> Any:
    half = theta / 2
    minus = torch.exp(torch.complex(torch.zeros_like(half), -half))
    plus = torch.exp(torch.complex(torch.zeros_like(half), half))
    zero = torch.zeros_like(minus)
    return torch.stack((torch.stack((minus, zero)), torch.stack((zero, plus))))


def _apply_single(state: Any, gate: Any, wire: int, n_qubits: int, torch: Any) -> Any:
    tensor = state.reshape([2] * n_qubits)
    moved = torch.movedim(tensor, wire, 0).reshape(2, -1)
    moved = gate @ moved
    moved = moved.reshape([2] + [2] * (n_qubits - 1))
    return torch.movedim(moved, 0, wire).reshape(-1)


def _apply_cnot(state: Any, control: int, target: int, n_qubits: int, torch: Any) -> Any:
    if control == target:
        raise ValueError("CNOT control và target phải khác nhau")
    tensor = state.reshape([2] * n_qubits)
    axes = [control, target] + [i for i in range(n_qubits) if i not in (control, target)]
    inverse = [0] * n_qubits
    for new_axis, old_axis in enumerate(axes):
        inverse[old_axis] = new_axis
    permuted = tensor.permute(axes).reshape(2, 2, -1)
    transformed = torch.stack(
        (
            torch.stack((permuted[0, 0], permuted[0, 1]), dim=0),
            torch.stack((permuted[1, 1], permuted[1, 0]), dim=0),
        ),
        dim=0,
    )
    transformed = transformed.reshape([2, 2] + [2] * (n_qubits - 2))
    return transformed.permute(inverse).reshape(-1)


def _expect_z(state: Any, wire: int, n_qubits: int, torch: Any) -> Any:
    probs = state.abs().pow(2).reshape([2] * n_qubits)
    other_axes = tuple(i for i in range(n_qubits) if i != wire)
    marginal = probs.sum(dim=other_axes) if other_axes else probs
    return marginal[0] - marginal[1]


def circuit_expectations(features: Any, theta: Any) -> Any:
    torch = _torch()
    n_qubits = int(features.shape[0])
    state = torch.zeros(2**n_qubits, dtype=torch.complex128, device=features.device)
    state[0] = 1.0 + 0.0j
    for wire in range(n_qubits):
        state = _apply_single(state, _ry(torch.pi * features[wire], torch), wire, n_qubits, torch)
    for layer in range(theta.shape[0]):
        for wire in range(n_qubits):
            state = _apply_single(state, _ry(theta[layer, wire, 0], torch), wire, n_qubits, torch)
            state = _apply_single(state, _rz(theta[layer, wire, 1], torch), wire, n_qubits, torch)
        for wire in range(n_qubits):
            state = _apply_cnot(state, wire, (wire + 1) % n_qubits, n_qubits, torch)
    return torch.stack([_expect_z(state, wire, n_qubits, torch) for wire in range(n_qubits)])


def score_vector(features: list[float], artifact: ModelArtifact) -> float:
    torch = _torch()
    if len(features) != artifact.n_qubits:
        raise QnnUnavailableError(
            f"QNN nhận {artifact.n_qubits} feature nhưng source đưa {len(features)}; cần train lại model."
        )
    x = torch.tensor(features, dtype=torch.float64)
    theta = torch.tensor(artifact.theta, dtype=torch.float64)
    readout = torch.tensor(artifact.readout, dtype=torch.float64)
    bias = torch.tensor(artifact.bias, dtype=torch.float64)
    q_values = circuit_expectations(x, theta)
    probability = torch.sigmoid(torch.dot(q_values, readout) + bias)
    return float(probability.detach().cpu().item())


def train_model(samples: list[dict[str, Any]], *, n_layers: int = 2, epochs: int = 100,
                learning_rate: float = 0.05, seed: int = 42) -> ModelArtifact:
    torch = _torch()
    if len(samples) < 4:
        raise ValueError("Cần ít nhất 4 review đã gắn nhãn để train QNN.")
    labels = [int(sample["label"]) for sample in samples]
    if len(set(labels)) < 2:
        raise ValueError("Dataset cần cả mẫu clean (0) và risky (1) trước khi train QNN.")
    n_qubits = len(FEATURE_NAMES)
    torch.manual_seed(seed)
    theta = torch.nn.Parameter(0.05 * torch.randn(n_layers, n_qubits, 2, dtype=torch.float64))
    readout = torch.nn.Parameter(0.05 * torch.randn(n_qubits, dtype=torch.float64))
    bias = torch.nn.Parameter(torch.zeros((), dtype=torch.float64))
    optimizer = torch.optim.Adam([theta, readout, bias], lr=learning_rate)
    criterion = torch.nn.BCEWithLogitsLoss()
    xs = [torch.tensor([float(s["features"][n]) for n in FEATURE_NAMES], dtype=torch.float64) for s in samples]
    ys = torch.tensor(labels, dtype=torch.float64)
    for _ in range(epochs):
        optimizer.zero_grad()
        logits = [torch.dot(circuit_expectations(x, theta), readout) + bias for x in xs]
        loss = criterion(torch.stack(logits), ys)
        loss.backward()
        optimizer.step()
    return ModelArtifact(
        n_qubits=n_qubits, n_layers=n_layers,
        theta=theta.detach().cpu().tolist(),
        readout=readout.detach().cpu().tolist(),
        bias=float(bias.detach().cpu().item()),
        trained_at=datetime.now(timezone.utc).isoformat(),
        samples=len(samples), risky_samples=sum(labels), clean_samples=len(labels)-sum(labels), seed=seed,
    )


def save_model(artifact: ModelArtifact, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": MODEL_SCHEMA_VERSION,
        "model_type": MODEL_TYPE,
        "feature_names": list(FEATURE_NAMES),
        "n_qubits": artifact.n_qubits,
        "n_layers": artifact.n_layers,
        "theta": artifact.theta,
        "readout": artifact.readout,
        "bias": artifact.bias,
        "trained_at": artifact.trained_at,
        "samples": artifact.samples,
        "risky_samples": artifact.risky_samples,
        "clean_samples": artifact.clean_samples,
        "seed": artifact.seed,
        "backend": BACKEND_NAME,
        "shots": None,
    }
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return target
