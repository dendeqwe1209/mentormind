"""spec 09 FR-02 — ``KNOWHOW_EVAL_JUDGE=ragas``: the ``ragas`` package behind the project's LLM and embedder."""

from __future__ import annotations

import os
from typing import Any

from langchain_core.prompt_values import StringPromptValue

from mentormind.core.providers.llm.backends.fake import FakeLLM
from mentormind.core.providers.llm.models import LLMResponse
from mentormind.core.schemas import DataClassification
from mentormind.evaluation.ragas import JudgeSample, RagasJudge
from mentormind.evaluation.ragas.judges.adapters import GuardedRagasLLM, ProjectEmbeddings
from tests.evaluation.fakes import SameVectorEmbedder, ScriptedJudge

SAMPLE = JudgeSample("Vì sao đặt nghiêng?", "Để tránh trầy [1].", ["Đặt nghiêng tránh trầy."], "Tránh trầy bề mặt.")


def test_ragas_analytics_are_off() -> None:
    assert os.environ["RAGAS_DO_NOT_TRACK"] == "true"


class LabelSpy(FakeLLM):
    labels: list[object]

    def generate(self, prompt: str, *, classification: Any, **kwargs: Any) -> LLMResponse:
        self.labels = [*getattr(self, "labels", []), classification]
        return super().generate(prompt, classification=classification, **kwargs)


def test_every_judge_prompt_goes_through_the_provider_with_the_run_label() -> None:
    llm = LabelSpy(["một", "hai"])
    result = GuardedRagasLLM(llm, DataClassification.SYNTHETIC).generate_text(StringPromptValue(text="p"), n=2)
    assert [g.text for g in result.generations[0]] == ["một", "hai"]
    assert llm.labels == [DataClassification.SYNTHETIC] * 2


def test_the_embeddings_are_the_project_embedder() -> None:
    embeddings = ProjectEmbeddings(SameVectorEmbedder())
    assert embeddings.embed_query("a") == [1.0, 0.0, 0.0]
    assert len(embeddings.embed_documents(["a", "b"])) == 2


def test_four_metrics_per_answer() -> None:
    [scores] = RagasJudge(ScriptedJudge(), SameVectorEmbedder()).score([SAMPLE], DataClassification.SYNTHETIC)
    assert scores == {"faithfulness": 0.75, "answer_relevancy": 1.0, "context_precision": 1.0, "context_recall": 1.0}


def test_a_metric_ragas_cannot_compute_is_empty_never_made_up() -> None:
    judge = RagasJudge(FakeLLM(["không phải JSON"] * 200), SameVectorEmbedder())
    [scores] = judge.score([SAMPLE], DataClassification.SYNTHETIC)
    assert set(scores.values()) == {None} and judge.failures == 4
