"""``knowhow eval report`` (spec 09 FR-04)."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Annotated

import typer

EVAL_DIR = Path("data/work/eval")


def report_cmd(
    run: Annotated[Path, typer.Option(help="Thư mục kết quả của `eval ragas`.")] = EVAL_DIR,
    review: Annotated[Path | None, typer.Option(help="review_stats.json (mặc định: trong --run nếu có).")] = None,
    sweep: Annotated[list[Path] | None, typer.Option(help="CSV của `vlm sweep` (lặp được).")] = None,
    out: Annotated[Path | None, typer.Option(help="File markdown.")] = None,
) -> None:
    from mentormind.evaluation.ragas import EvalSummary, read_results
    from mentormind.evaluation.report import build_report
    from mentormind.evaluation.review import ReviewStats

    summary_file = run / "summary.json"
    if not summary_file.is_file():
        typer.secho(
            f"Lỗi: chưa có {summary_file}; chạy `knowhow eval ragas` trước.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)
    summary = EvalSummary.model_validate_json(summary_file.read_text(encoding="utf-8"))
    review_file = review or run / "review_stats.json"
    stats = ReviewStats.model_validate_json(review_file.read_text(encoding="utf-8")) if review_file.is_file() else None
    rows: list[dict[str, str]] = []
    for path in sweep or []:
        with path.open(encoding="utf-8") as handle:
            rows += list(csv.DictReader(handle))
    target = out or run / "usefulness_report.md"
    target.write_text(
        build_report(summary, read_results(run / "ragas_results.csv"), stats, rows),
        encoding="utf-8",
    )
    typer.echo(f"Báo cáo: {target}")
