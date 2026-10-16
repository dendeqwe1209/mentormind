"""spec 06 §3 — Work Assistant: three guards (RRF floor, cosine gate, LLM JSON) and the post-check."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mentormind.agents.base import TraceLog
from mentormind.agents.work_assistant import ANSWER_SCHEMA, REFUSAL, WorkAssistant
from mentormind.core.guard import GuardPolicy
from mentormind.core.providers.llm.backends.fake import FakeLLM
from mentormind.core.schemas import DataClassification
from mentormind.core.schemas.agents import AskRequest
from mentormind.knowledge_base.retrieval.hybrid import RetrievedContext
from tests.agents.fakes import REASON_PROFILE, FakeEmbedder, FakeExperts, FakeRetriever, context, reply

SYN = DataClassification.SYNTHETIC
SECRET = DataClassification.FACTORY_CONFIDENTIAL
ASK = AskRequest(question="Vì sao phải đặt linh kiện A nghiêng?", process_id="PACK01")
# RRF scores as spec 05 returns them (~0.133 at most).
TWO = context(
    (*REASON_PROFILE, 0.1328, SYN),
    ("WP-PACK01-004", "Bước: Đậy nắp hộp. Thao tác: ấn đều hai góc.", 0.1161, SYN),
)
REASON = "Đặt nghiêng để tránh trầy bề mặt khi đóng nắp hộp [1]."


def assistant(llm: FakeLLM, result: RetrievedContext, tmp_path: Path, embedder: Any = None) -> WorkAssistant:
    return WorkAssistant(
        FakeRetriever(result),
        llm,
        embedder=embedder or FakeEmbedder(),
        experts=FakeExperts({"PACK01": "Nguyễn Văn A"}),
        trace=TraceLog(tmp_path / "traces"),
    )


def trace_metrics(tmp_path: Path) -> dict[str, Any]:
    [line] = (tmp_path / "traces").glob("ask-*.jsonl")
    metrics: dict[str, Any] = json.loads(line.read_text(encoding="utf-8").splitlines()[-1])["metrics"]
    return metrics


def ask(question: str) -> AskRequest:
    return AskRequest(question=question, process_id="PACK01")


def test_ac_01_no_context_means_refusal_with_the_expert_to_ask(tmp_path: Path) -> None:
    llm = FakeLLM(["không được gọi"])
    empty = RetrievedContext(
        query="q", process_id="PACK01", passages=[], graph_facts=[], citations=[], classifications=[]
    )
    answer = assistant(llm, empty, tmp_path).ask(ASK)
    assert answer.refused and answer.answer == REFUSAL
    assert answer.suggested_contact == "Nguyễn Văn A"
    assert llm.calls == []


def test_ac_09_an_rrf_score_below_the_floor_refuses_before_embedding_or_the_llm(tmp_path: Path) -> None:
    weak = context(("WP-PACK01-009", "Bước: Đặt hộp lên bàn.", 0.01, SYN))
    llm, embedder = FakeLLM([reply("x [1]", [1])]), FakeEmbedder()
    answer = assistant(llm, weak, tmp_path, embedder).ask(ASK)
    assert answer.refused and llm.calls == [] and embedder.calls == 0
    assert trace_metrics(tmp_path) == {"max_rrf": 0.01, "blocked_by": "rrf"}


def test_ac_10_an_off_topic_question_is_refused_without_calling_the_llm(tmp_path: Path) -> None:
    # Live LASI run 2026-10-04: this question had RRF 0.116, close to an on-topic 0.133.
    llm = FakeLLM([reply("Không có thông tin [1].", [1])])
    answer = assistant(llm, TWO, tmp_path).ask(ask("Giá cổ phiếu DENSO hôm nay?"))
    assert answer.refused and llm.calls == []
    assert trace_metrics(tmp_path)["blocked_by"] == "cosine"


def test_ac_10_an_on_topic_question_in_other_words_passes_the_cosine_gate(tmp_path: Path) -> None:
    llm = FakeLLM([reply("Đặt linh kiện A nghiêng vào ngăn trái [1].", [1])])
    answer = assistant(llm, TWO, tmp_path).ask(ask("Bỏ sản phẩm vào thùng thế nào?"))
    assert not answer.refused and len(llm.calls) == 1
    assert trace_metrics(tmp_path) == {"max_rrf": 0.1328, "max_cosine": 1.0, "blocked_by": None}


def test_ac_11_an_unanswerable_question_is_refused_without_a_retry(tmp_path: Path) -> None:
    # A "why" the sources do not state: the LLM says so instead of inventing a reason.
    no_reason = context(("WP-PACK01-001", "Bước: Đặt linh kiện vào hộp theo thứ tự từ trái sang phải.", 0.13, SYN))
    llm = FakeLLM([reply("", [], answerable=False)])
    answer = assistant(llm, no_reason, tmp_path).ask(ask("Vì sao đặt từ trái sang phải?"))
    assert answer.refused and answer.suggested_contact == "Nguyễn Văn A" and len(llm.calls) == 1
    assert trace_metrics(tmp_path)["blocked_by"] == "llm_unanswerable"


def test_ac_12_markers_that_do_not_match_used_sources_are_retried_then_refused(tmp_path: Path) -> None:
    # The live LASI failure: "no information" plus markers [1]..[n] slipped through the old check.
    llm = FakeLLM([reply("Đặt nghiêng [1]. Đậy nắp [2].", [1]), reply("Đặt nghiêng [1].", [1, 2])])
    answer = assistant(llm, TWO, tmp_path).ask(ASK)
    assert len(llm.calls) == 2 and answer.refused
    assert trace_metrics(tmp_path)["blocked_by"] == "post_check"


def test_ac_02_a_source_number_that_does_not_exist_is_retried_then_refused(tmp_path: Path) -> None:
    llm = FakeLLM([reply("Đặt nghiêng để tránh trầy [3].", [3]), reply("Vẫn sai [3].", [3])])
    answer = assistant(llm, TWO, tmp_path).ask(ASK)
    assert len(llm.calls) == 2 and answer.refused
    assert answer.suggested_contact == "Nguyễn Văn A"


def test_ac_02_an_unreadable_answer_gets_one_retry(tmp_path: Path) -> None:
    llm = FakeLLM(["không phải JSON", reply(REASON, [1])])
    answer = assistant(llm, TWO, tmp_path).ask(ASK)
    assert len(llm.calls) == 2 and not answer.refused


def test_ac_03_the_reason_is_answered_with_the_right_profile(tmp_path: Path) -> None:
    llm = FakeLLM([reply(REASON, [1])])
    answer = assistant(llm, TWO, tmp_path).ask(ASK)
    assert not answer.refused
    assert "tránh trầy bề mặt khi đóng nắp hộp" in answer.answer
    assert answer.citations[0].ref_id == "WP-PACK01-003"
    assert answer.confidence == 1.0  # mean cosine of the sources actually used
    assert "Lý do: tránh trầy bề mặt" in llm.calls[0].prompt  # the reason reached the prompt
    assert llm.calls[0].json_schema == ANSWER_SCHEMA


def test_ac_04_a_cloud_llm_never_sees_a_confidential_passage(tmp_path: Path) -> None:
    mixed = context(
        (*REASON_PROFILE, 0.1328, SYN),
        ("WP-LINE3-004", "Bước: Chỉnh lực kẹp 12 N ở trạm 3, đặt hộp.", 0.13, SECRET),
    )
    llm = FakeLLM([reply(REASON, [1])], name="qwen_api", is_cloud=True)
    llm.guard_policy = GuardPolicy(audit_dir=None)
    answer = assistant(llm, mixed, tmp_path).ask(ASK)
    sent = llm.calls[0].prompt
    assert "Chỉnh lực kẹp" not in sent and "WP-LINE3-004" not in sent
    assert [c.ref_id for c in answer.citations] == ["WP-PACK01-003"]


def test_passages_without_a_label_are_treated_as_confidential(tmp_path: Path) -> None:
    unlabelled = TWO.model_copy(update={"classifications": []})
    llm = FakeLLM([reply("x [1]", [1])], name="qwen_api", is_cloud=True)
    llm.guard_policy = GuardPolicy(audit_dir=None)
    answer = assistant(llm, unlabelled, tmp_path).ask(ASK)
    assert answer.refused and llm.calls == []  # nothing is left to send to the cloud


def test_every_call_leaves_a_trace(tmp_path: Path) -> None:
    llm = FakeLLM([reply(REASON, [1])])
    assistant(llm, TWO, tmp_path).ask(ASK)
    [line] = (tmp_path / "traces").glob("ask-*.jsonl")
    record = line.read_text(encoding="utf-8")
    assert '"WP-PACK01-003"' in record and '"sha256:' in record and '"refused": false' in record


def test_the_prompt_forbids_a_reason_the_sources_do_not_state(tmp_path: Path) -> None:
    # Live test 2026-10-04: a source without a reason got "Đây là quy trình chuẩn để ..." (art. 3).
    llm = FakeLLM([reply("Đặt nghiêng [1].", [1])])
    assistant(llm, TWO, tmp_path).ask(ASK)
    prompt = llm.calls[0].prompt
    assert "KHÔNG tự suy ra hay thêm lý do" in prompt
    assert 'hỏi "vì sao" mà nguồn không ghi lý do' in prompt  # -> answerable = false


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
