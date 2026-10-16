"""``knowhow agent rca`` (spec 06 FR-03)."""

from __future__ import annotations

from typing import Annotated

import typer


def rca_cmd(
    lot: Annotated[str | None, typer.Option("--lot", help="Mã lot trong Sigma.")] = None,
    symptom: Annotated[str | None, typer.Option("--symptom", help="Mô tả triệu chứng.")] = None,
    process: Annotated[str | None, typer.Option("--process", help="Mã công đoạn.")] = None,
) -> None:
    from pydantic import ValidationError

    from mentormind.agents.adapters.factory import AgentWiringError, build_rca_agent
    from mentormind.core.config import get_settings
    from mentormind.core.guard import ConfidentialDataError
    from mentormind.core.providers.errors import ProviderError
    from mentormind.core.schemas.agents import RcaRequest
    from mentormind.knowledge_base.sigma.adapter import LotNotFound

    try:
        request = RcaRequest(lot_id=lot, symptom_text=symptom, process_id=process)
        report = build_rca_agent(get_settings()).investigate(request)
    except ValidationError as exc:
        typer.secho("Lỗi: cần --lot hoặc --symptom.", fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from exc
    except LotNotFound as exc:
        typer.secho(f"Lỗi: không tìm thấy lot {lot!r} trong Sigma.", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    except (AgentWiringError, ProviderError, ConfidentialDataError) as exc:
        typer.secho(f"Lỗi: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    typer.echo(report.model_dump_json(indent=2))
