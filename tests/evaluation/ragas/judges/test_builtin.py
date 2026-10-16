"""spec 09 FR-02 — ``KNOWHOW_EVAL_JUDGE=builtin``: the four metrics with the project's own prompts."""

from __future__ import annotations

import pytest

from mentormind.core.guard import ConfidentialDataError
from mentormind.core.providers.llm.backends.fake import FakeLLM
from mentormind.core.schemas import DataClassification
from mentormind.evaluation.ragas import BuiltinJudge, JudgeSample
from tests.evaluation.fakes import SameVectorEmbedder, ScriptedJudge

SAMPLE = JudgeSample("Vì sao đặt nghiêng?", "Để tránh trầy [1].", ["Đặt nghiêng tránh trầy."], "Tránh trầy bề mặt.")


def test_four_metrics_per_answer() -> None:
    [scores] = BuiltinJudge(ScriptedJudge(), SameVectorEmbedder()).score([SAMPLE], DataClassification.SYNTHETIC)
    assert scores == {"faithfulness": 0.75, "answer_relevancy": 1.0, "context_precision": 1.0, "context_recall": 1.0}


def test_every_judge_call_goes_through_the_provider_with_a_json_schema() -> None:
    llm = ScriptedJudge()
    BuiltinJudge(llm, SameVectorEmbedder()).score([SAMPLE], DataClassification.SYNTHETIC)
    assert len(llm.calls) == 4 and all(call.json_schema for call in llm.calls)


def test_a_noncommittal_answer_is_not_relevant() -> None:
    llm = FakeLLM([{"claims": []}, {"questions": ["q"], "noncommittal": True}, {"verdicts": []}, {"sentences": []}])
    [scores] = BuiltinJudge(llm, SameVectorEmbedder()).score([SAMPLE], DataClassification.SYNTHETIC)
    assert scores["answer_relevancy"] == 0.0


def test_a_metric_the_judge_cannot_answer_is_empty_never_made_up() -> None:
    judge = BuiltinJudge(FakeLLM(["không phải JSON"]), SameVectorEmbedder())
    [scores] = judge.score([SAMPLE], DataClassification.SYNTHETIC)
    assert set(scores.values()) == {None} and judge.failures == 4


def test_confidential_data_never_reaches_a_cloud_judge() -> None:
    judge = BuiltinJudge(FakeLLM(is_cloud=True), SameVectorEmbedder())
    with pytest.raises(ConfidentialDataError):
        judge.score([SAMPLE], DataClassification.FACTORY_CONFIDENTIAL)
