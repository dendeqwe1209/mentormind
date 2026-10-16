"""The agents behind the REST routers of spec 08 (``/assistant/ask``, ``/rca/investigate``).

The routers call ``mentormind.agents.supervisor.ask`` and ``mentormind.agents.rca.investigate``
with the API models of ``core.schemas.api`` and fall back to their demo answer on ``ImportError``.
This module translates between those models and the agents' own (spec 06 §3, §4):

* ``KNOWHOW_API_AGENTS=mock`` (default) raises ``AgentsOffline`` (an ``ImportError``), so the
  routers keep their demo answers;
* ``live`` runs the agents: an unknown lot is a 404, a missing component or LLM a 503.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import TypeVar

from pydantic import ValidationError

from mentormind.agents.adapters.factory import AgentWiringError, build_rca_agent, build_work_assistant
from mentormind.agents.rca import RcaAgent
from mentormind.agents.work_assistant import WorkAssistant
from mentormind.core.config import get_settings
from mentormind.core.guard import ConfidentialDataError
from mentormind.core.providers.errors import ProviderError
from mentormind.core.schemas import Citation, WorkProfile, api
from mentormind.core.schemas import agents as spec06

T = TypeVar("T")


class AgentsOffline(ImportError):
    """``KNOWHOW_API_AGENTS=mock``: the router answers with its demo data."""


def ask(request: api.AskRequest) -> api.AssistantAnswer:
    answer = _call(lambda: _assistant().ask(to_ask(request)))
    return from_answer(answer)


def investigate(request: api.RcaRequest) -> api.RcaReport:
    from fastapi import HTTPException, status

    from mentormind.knowledge_base.sigma.adapter import LotNotFound

    try:
        spec_request = to_rca(request)
    except ValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cần cung cấp lot_id hoặc mô tả triệu chứng lỗi.") from exc
    try:
        report = _call(lambda: _rca_agent().investigate(spec_request))
    except LotNotFound as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Không tìm thấy lô sản xuất với lot_id: {request.lot_id}"
        ) from exc
    return from_report(report)


def to_ask(request: api.AskRequest) -> spec06.AskRequest:
    return spec06.AskRequest(question=request.question, process_id=request.process_id or None)


def from_answer(answer: spec06.AssistantAnswer) -> api.AssistantAnswer:
    return api.AssistantAnswer(
        answer=answer.answer,
        refused=answer.refused,
        suggested_expert=answer.suggested_contact,
        citations=[for_ui(c) for c in answer.citations],
    )


def for_ui(citation: Citation) -> Citation:
    """What page 2 shows for a citation (spec 08 §3, AC-16).

    The agent puts the cited text in ``snippet``; the UI reads ``excerpt``. A cited profile also gets
    its step as ``title``, its time span, and a keyframe served by ``GET /media``.
    """
    update: dict[str, object] = {}
    if not citation.excerpt and citation.snippet:
        update["excerpt"] = citation.snippet
    profile = _stored_profile(citation.ref_id) if citation.source_type == "work_profile" else None
    if profile is not None:
        evidence = profile.evidence
        update["title"] = citation.title or profile.step
        update["t_start"] = evidence.t_start if citation.t_start is None else citation.t_start
        update["t_end"] = evidence.t_end if citation.t_end is None else citation.t_end
        if not citation.keyframe_url and evidence.keyframes:
            # The middle keyframe of the step's first segment (spec 03 FR-05 order: start, middle, end).
            update["keyframe_url"] = _media_url(evidence.keyframes[min(1, len(evidence.keyframes) - 1)])
    return citation.model_copy(update=update)


def _stored_profile(profile_id: str) -> WorkProfile | None:
    from mentormind.knowledge_base.store.profile_store import ProfileStore

    db = Path(get_settings().profile_db)
    if not db.is_file():  # no store yet: never create one from here
        return None
    try:
        return ProfileStore(db_path=str(db)).get_profile(profile_id)
    except (sqlite3.Error, ValueError):  # a broken row only costs the citation its details
        return None


def _media_url(path: str) -> str | None:
    """``GET /media`` URL of a file under the work or samples dir (spec 08 §2), else ``None``."""
    settings = get_settings()
    file = Path(path).resolve()
    for base in (settings.work_dir, settings.samples_dir):
        if file.is_relative_to(Path(base).resolve()):
            return "/media/" + file.relative_to(Path(base).resolve()).as_posix()
    return None


def to_rca(request: api.RcaRequest) -> spec06.RcaRequest:
    return spec06.RcaRequest(lot_id=request.lot_id, symptom_text=request.symptom)


def from_report(report: spec06.RcaReport) -> api.RcaReport:
    return api.RcaReport(
        lot_id=report.lot_id,
        symptom=report.symptom,
        hypotheses=[
            api.Hypothesis(
                hypothesis=h.cause,
                likelihood=h.likelihood,
                evidence_refs=[c.ref_id for c in h.evidence],
            )
            for h in report.hypotheses
        ],
        five_whys=[
            api.WhyStep(order=i, question=w.why, answer=w.answer, verified=w.verified)
            for i, w in enumerate(report.five_why, start=1)
        ],
        related_lots=report.related_lots,
        preventive_actions=report.prevention_steps,
        disclaimer=report.disclaimer,
    )


def _call(run: Callable[[], T]) -> T:
    from fastapi import HTTPException, status

    if get_settings().api_agents != "live":
        raise AgentsOffline("KNOWHOW_API_AGENTS=mock")
    try:
        return run()
    except (AgentWiringError, ProviderError, ConfidentialDataError) as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Agent chưa sẵn sàng: {exc}") from exc


@lru_cache(maxsize=1)
def _assistant() -> WorkAssistant:
    return build_work_assistant(get_settings())


@lru_cache(maxsize=1)
def _rca_agent() -> RcaAgent:
    return build_rca_agent(get_settings())
