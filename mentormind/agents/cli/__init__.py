"""``knowhow agent ...`` (spec 06 FR-03): one module per command."""

from __future__ import annotations

import typer

from mentormind.agents.cli.ask import ask_cmd
from mentormind.agents.cli.rca import rca_cmd

app = typer.Typer(help="Work Assistant và RCA Agent (spec 06).", no_args_is_help=True)
app.command("ask", help="Hỏi trợ lý về một bước thao tác; trả lời có trích nguồn hoặc từ chối.")(ask_cmd)
app.command("rca", help="Truy nguyên nhân lỗi theo lot (Sigma) hoặc triệu chứng; in báo cáo JSON.")(rca_cmd)

__all__ = ["app"]
