"""``knowhow agent ask`` (spec 06 FR-03)."""

from __future__ import annotations

from typing import Annotated

import typer


def ask_cmd(
    question: Annotated[str, typer.Argument(help="Câu hỏi.")],
    process: Annotated[str | None, typer.Option("--process", help="Mã công đoạn.")] = None,
) -> None:
    from mentormind.agents.adapters.factory import AgentWiringError, build_work_assistant
    from mentormind.core.config import get_settings
    from mentormind.core.guard import ConfidentialDataError
    from mentormind.core.providers.errors import ProviderError
    from mentormind.core.schemas.agents import AskRequest

    try:
        answer = build_work_assistant(get_settings()).ask(AskRequest(question=question, process_id=process))
    except (AgentWiringError, ProviderError, ConfidentialDataError) as exc:
        typer.secho(f"Lỗi: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    typer.echo(answer.answer)
    if answer.refused:
        if answer.suggested_contact:
            typer.echo(f"Hỏi chuyên gia: {answer.suggested_contact}")
        return
    for i, c in enumerate(answer.citations, start=1):
        typer.echo(f"[{i}] {c.source_type} {c.ref_id}: {c.snippet}")
    typer.echo(f"độ tin cậy: {answer.confidence:.2f}")
