"""Train and inspect classical CPU-only review-risk models."""
from __future__ import annotations

import json
from pathlib import Path

import typer

from mentormind.core.config import get_settings
from mentormind.nn.model import ModelArtifact, ModelUnavailableError, save_model, train_model
from mentormind.qnn.snapshot_store import ReviewRiskDatasetStore

app = typer.Typer(
    help="Classical NN review-risk (QNN remains a separate research baseline).",
    no_args_is_help=True,
)


@app.command("status")
def status() -> None:
    settings = get_settings()
    counts = ReviewRiskDatasetStore(settings.profile_db).counts()
    typer.echo(f"nn_enabled: {settings.nn_enabled}")
    typer.echo(f"model_exists: {settings.nn_model_path.is_file()}")
    typer.echo(f"labeled: {counts['labeled']} (risky={counts['risky']}, clean={counts['clean']})")
    if settings.nn_model_path.is_file():
        try:
            metrics = ModelArtifact.load(settings.nn_model_path).validation_metrics
            typer.echo(json.dumps(metrics, indent=2))
        except ModelUnavailableError as exc:
            typer.echo(f"model_error: {exc}")


@app.command("train")
def train(
    epochs: int = typer.Option(240, min=1, max=2000),
    hidden_units: int = typer.Option(12, min=1, max=64),
    learning_rate: float = typer.Option(0.025, "--lr", min=0.000001, max=1.0),
    seed: int = typer.Option(42),
    output: Path | None = typer.Option(None, "--output", "-o"),
) -> None:
    settings = get_settings()
    samples = ReviewRiskDatasetStore(settings.profile_db).labeled_samples()
    try:
        model = train_model(samples, epochs=epochs, hidden_units=hidden_units,
                            learning_rate=learning_rate, seed=seed)
        path = save_model(model, output or settings.nn_model_path)
    except (ValueError, ModelUnavailableError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Saved NN artifact: {path}")
    typer.echo(f"Stratified validation (n={model.validation_samples}, not a production benchmark):")
    typer.echo(json.dumps(model.validation_metrics, indent=2))


if __name__ == "__main__":
    app()
