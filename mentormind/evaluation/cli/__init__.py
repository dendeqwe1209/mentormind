"""``knowhow eval ...`` (spec 09): one module per command."""

from __future__ import annotations

import typer

from mentormind.evaluation.cli.ragas import ragas_cmd
from mentormind.evaluation.cli.report import report_cmd
from mentormind.evaluation.cli.review import review_stats_cmd

app = typer.Typer(help="Đánh giá Ragas và báo cáo mức độ hữu ích (spec 09).", no_args_is_help=True)
app.command("ragas", help="Chạy trợ lý trên golden set, chấm 4 chỉ số Ragas + 2 chỉ số tự tính.")(ragas_cmd)
app.command("review-stats", help="Tỷ lệ duyệt/sửa/từ chối, error_tags, reason_coverage.")(review_stats_cmd)
app.command("report", help="Gộp kết quả Ragas + review-stats + sweep thành usefulness_report.md.")(report_cmd)

__all__ = ["app"]
