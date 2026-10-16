"""CLI for collecting, inspecting and training the review-risk QNN."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from mentormind.core.config import get_settings
from mentormind.qnn.model import QnnUnavailableError, save_model, train_model
from mentormind.qnn.snapshot_store import ReviewRiskDatasetStore

app = typer.Typer(help="QNN ưu tiên Human Review theo review-risk.", no_args_is_help=True)


@app.command("status")
def status() -> None:
    settings = get_settings()
    dataset = ReviewRiskDatasetStore(settings.profile_db)
    counts = dataset.counts()
    typer.echo(f"enabled: {settings.qnn_enabled}")
    typer.echo(f"model: {settings.qnn_model_path} ({'exists' if settings.qnn_model_path.is_file() else 'missing'})")
    typer.echo(
        f"samples: total={counts['total']} labeled={counts['labeled']} risky={counts['risky']} clean={counts['clean']}"
    )


@app.command("dataset")
def dataset(output: Path | None = typer.Option(None, "--output", "-o")) -> None:
    settings = get_settings()
    rows = ReviewRiskDatasetStore(settings.profile_db).labeled_samples()
    payload = json.dumps(rows, ensure_ascii=False, indent=2)
    if output is None:
        typer.echo(payload)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
        typer.echo(f"Đã ghi {len(rows)} mẫu: {output}")


@app.command("train")
def train(
    epochs: int = typer.Option(100, min=1, help="Số epoch."),
    learning_rate: float = typer.Option(0.05, "--lr", min=0.000001, help="Adam learning rate."),
    seed: int = typer.Option(42, help="Random seed."),
) -> None:
    settings = get_settings()
    samples = ReviewRiskDatasetStore(settings.profile_db).labeled_samples()
    try:
        artifact = train_model(
            samples,
            n_layers=settings.qnn_layers,
            epochs=epochs,
            learning_rate=learning_rate,
            seed=seed,
        )
    except (ValueError, QnnUnavailableError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    path = save_model(artifact, settings.qnn_model_path)
    typer.echo(
        f"QNN trained: samples={artifact.samples} risky={artifact.risky_samples} clean={artifact.clean_samples} "
        f"qubits={artifact.n_qubits} layers={artifact.n_layers} -> {path}"
    )
