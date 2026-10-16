"""spec 06 FR-04 — every agent runs through ``Agent.run``: one trace line per call, every prompt in it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mentormind.agents.base import Agent, AgentRun, PromptBook, TraceLog, prompt_hash
from mentormind.core.providers.llm.backends.fake import FakeLLM
from mentormind.core.schemas import DataClassification
from mentormind.core.schemas.agents import AskRequest, AssistantAnswer
from tests.agents.fakes import context

PUBLIC, SECRET = DataClassification.PUBLIC, DataClassification.FACTORY_CONFIDENTIAL


class Echo(Agent[AskRequest, AssistantAnswer]):
    """Asks the LLM twice and answers with the second reply."""

    kind = "echo"
    prompts = PromptBook(Path("."))

    def _run(self, request: AskRequest, call: AgentRun) -> AssistantAnswer:
        call.context_ids = ["WP-PACK01-001"]
        self.generate(call, f"1: {request.question}", classification=PUBLIC)
        text = self.generate(call, f"2: {request.question}", classification=PUBLIC).text
        if text == "lỗi":
            raise RuntimeError(text)
        return AssistantAnswer(answer=text, confidence=1.0, refused=False)


def test_one_trace_line_per_call_with_every_prompt(tmp_path: Path) -> None:
    answer = Echo(FakeLLM(["a", "b"]), trace=TraceLog(tmp_path)).run(AskRequest(question="q"))
    [line] = (tmp_path / next(p.name for p in tmp_path.iterdir())).read_text(encoding="utf-8").splitlines()
    record = json.loads(line)
    assert answer.answer == "b" and record["kind"] == "echo" and record["llm"] == "fake"
    assert record["prompt_hashes"] == [prompt_hash("1: q"), prompt_hash("2: q")]
    assert record["context_ids"] == ["WP-PACK01-001"] and record["response"]["answer"] == "b"


def test_a_failed_call_leaves_no_trace(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        Echo(FakeLLM(["a", "lỗi"]), trace=TraceLog(tmp_path)).run(AskRequest(question="q"))
    assert not list(tmp_path.iterdir())


def test_a_cloud_llm_never_gets_confidential_or_unlabelled_passages() -> None:
    retrieved = context(("WP-A", "công khai", 0.9, PUBLIC), ("WP-B", "bí mật", 0.9, SECRET))
    retrieved.classifications.pop()  # WP-B now has no label at all: fail closed
    cloud = Echo(FakeLLM(is_cloud=True)).allowed_passages(retrieved)
    local = Echo(FakeLLM()).allowed_passages(retrieved)
    assert [c.ref_id for _, c in cloud] == ["WP-A"]
    assert [c.ref_id for _, c in local] == ["WP-A", "WP-B"]
