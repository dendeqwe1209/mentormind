"""RCA Agent (spec 06 §4): a lot or a symptom in, cause hypotheses and a 5-Why draft out."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mentormind.agents.rca.agent import RcaAgent
from mentormind.agents.rca.report import DISCLAIMER, RCA_SCHEMA

if TYPE_CHECKING:
    from mentormind.core.schemas.api import RcaReport, RcaRequest

__all__ = ["DISCLAIMER", "RCA_SCHEMA", "RcaAgent", "investigate"]


def investigate(request: RcaRequest) -> RcaReport:
    """Entry point of ``POST /rca/investigate`` (spec 08), see ``mentormind.agents.adapters.rest``."""
    # Imported here: ``adapters.rest`` builds on ``adapters.factory``, which imports this package.
    from mentormind.agents.adapters.rest import investigate as run

    return run(request)
