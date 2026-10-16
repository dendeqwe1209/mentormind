"""``knowhow eval review-stats`` (spec 09 FR-03)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

EVAL_DIR = Path("data/work/eval")


def review_stats_cmd(
    db: Annotated[Path | None, typer.Option(help="Profile store (mặc định KNOWHOW_PROFILE_DB).")] = None,
    out: Annotated[Path, typer.Option(help="File JSON kết quả.")] = EVAL_DIR / "review_stats.json",
) -> None:
    from mentormind.core.config import get_settings
    from mentormind.evaluation.review import read_store, review_stats

    path = db or get_settings().profile_db
    if not path.is_file():
        typer.secho(f"Lỗi: chưa có profile store {path} (spec 08).", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    stats = review_stats(*read_store(path))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(stats.model_dump_json(indent=2), encoding="utf-8")
    typer.echo(stats.model_dump_json(indent=2))
