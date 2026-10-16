"""spec 01 AC-03 — ``knowhow --help`` lists every module sub-command."""

from __future__ import annotations

from typer.testing import CliRunner

from mentormind.core.cli import app


def test_ac_03_help_lists_module_subcommands() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("ingest", "video", "vlm", "kg", "agent", "sigma", "eval"):
        assert command in result.output
