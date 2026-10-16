"""spec 06 T06-4 — ``knowhow agent ask|rca``."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from mentormind.agents.adapters import factory
from mentormind.agents.rca import RcaAgent
from mentormind.agents.work_assistant import WorkAssistant
from mentormind.core.cli import app
from mentormind.core.providers.llm.backends.fake import FakeLLM
from mentormind.core.schemas import DataClassification
from tests.agents.fakes import REASON_PROFILE, FakeEmbedder, FakeGraph, FakeRetriever, FakeSigma, context, reply

runner = CliRunner()


def test_ask_prints_the_answer_and_its_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed = WorkAssistant(
        FakeRetriever(context((*REASON_PROFILE, 0.8, DataClassification.SYNTHETIC))),
        FakeLLM([reply("Đặt nghiêng để tránh trầy bề mặt [1].", [1])]),
        embedder=FakeEmbedder(),
    )
    monkeypatch.setattr(factory, "build_work_assistant", lambda settings: fixed)
    result = runner.invoke(app, ["agent", "ask", "Vì sao đặt nghiêng?", "--process", "PACK01"])
    assert result.exit_code == 0, result.output
    assert "tránh trầy" in result.output and "[1] work_profile WP-PACK01-003" in result.output


def test_an_unknown_lot_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    rca = RcaAgent(FakeLLM([]), FakeGraph({}, {}), FakeRetriever(context()), FakeSigma([], []))
    monkeypatch.setattr(factory, "build_rca_agent", lambda settings: rca)
    result = runner.invoke(app, ["agent", "rca", "--lot", "L-1"])
    assert result.exit_code == 1 and "không tìm thấy lot 'L-1'" in result.output


def test_a_missing_component_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(settings: object) -> WorkAssistant:
        raise factory.AgentWiringError("Thiếu thư viện của spec 05 (neo4j): uv sync --extra kg.")

    monkeypatch.setattr(factory, "build_work_assistant", missing)
    result = runner.invoke(app, ["agent", "ask", "Vì sao?"])
    assert result.exit_code == 1 and "spec 05" in result.output


def test_rca_needs_a_lot_or_a_symptom() -> None:
    result = runner.invoke(app, ["agent", "rca"])
    assert result.exit_code == 2 and "--lot" in result.output


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
