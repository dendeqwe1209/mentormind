"""Root ``knowhow`` CLI (spec 01 FR-02/AC-03): one sub-command group per module.

Each module owns its Typer app; groups whose tasks have not landed yet are empty placeholders.
"""

from __future__ import annotations

import typer

from mentormind.agents.cli import app as agent_app
from mentormind.capture.ingest.cli import app as ingest_app
from mentormind.capture.video.cli import app as video_app
from mentormind.evaluation.cli import app as eval_app
from mentormind.knowledge_base.kg.cli import app as kg_app
from mentormind.processing.vlm.cli import app as vlm_app

app = typer.Typer(help="Mentor Mind — tích lũy bí quyết chuyên gia cho AI.", no_args_is_help=True)

_PLACEHOLDERS = {
    "sigma": "Adapter dữ liệu Sigma (spec 07).",
}

for _name, _help in _PLACEHOLDERS.items():
    app.add_typer(typer.Typer(help=_help, no_args_is_help=True), name=_name)
app.add_typer(video_app, name="video")
app.add_typer(ingest_app, name="ingest")
app.add_typer(vlm_app, name="vlm")
app.add_typer(kg_app, name="kg")
app.add_typer(agent_app, name="agent")
app.add_typer(eval_app, name="eval")


if __name__ == "__main__":
    app()
