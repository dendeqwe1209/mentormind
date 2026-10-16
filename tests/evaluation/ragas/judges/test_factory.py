"""spec 09 §5b — ``KNOWHOW_EVAL_JUDGE`` picks the judge; both score the same answers alike."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from mentormind.core.config import Settings
from mentormind.core.schemas import DataClassification
from mentormind.evaluation.ragas import JUDGES, Judge, JudgeConfigError, JudgeSample, RagasJudge, build_judge
from mentormind.evaluation.ragas.judges import factory
from tests.evaluation.fakes import SameVectorEmbedder, ScriptedJudge

SAMPLE = JudgeSample("Vì sao đặt nghiêng?", "Để tránh trầy [1].", ["Đặt nghiêng tránh trầy."], "Tránh trầy bề mặt.")


@pytest.mark.parametrize("name", sorted(JUDGES))
def test_each_judge_gives_the_same_scores_for_the_same_judge_answers(name: str) -> None:
    judge = build_judge(name, ScriptedJudge(), SameVectorEmbedder())
    assert judge.kind == name
    [scores] = judge.score([SAMPLE], DataClassification.SYNTHETIC)
    assert scores == {"faithfulness": 0.75, "answer_relevancy": 1.0, "context_precision": 1.0, "context_recall": 1.0}


def test_the_ragas_package_is_the_default_judge() -> None:
    assert Settings(_env_file=None).eval_judge == "ragas"


def test_an_unknown_judge_is_refused() -> None:
    with pytest.raises(JudgeConfigError, match="builtin, ragas"):
        build_judge("gpt", ScriptedJudge(), SameVectorEmbedder())


def test_the_ragas_judge_without_the_eval_extra_says_how_to_fix_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(factory, "find_spec", lambda name: None)
    with pytest.raises(JudgeConfigError, match="--extra eval"):
        build_judge("ragas", ScriptedJudge(), SameVectorEmbedder())


def test_a_new_judge_is_one_subclass_and_its_gaps_are_counted() -> None:
    class Half(Judge):
        kind = "half-test"

        def _score(self, samples: Sequence[JudgeSample], label: DataClassification) -> list[dict[str, float | None]]:
            return [{"faithfulness": 0.5, "answer_relevancy": None} for _ in samples]

    try:
        judge = build_judge("half-test", ScriptedJudge(), SameVectorEmbedder())
        assert isinstance(judge, Half)
        assert judge.score([SAMPLE, SAMPLE], DataClassification.SYNTHETIC)[0]["faithfulness"] == 0.5
        assert judge.failures == 2 and judge.score([], DataClassification.SYNTHETIC) == []
    finally:
        Judge.registry.pop("half-test")


def test_the_ragas_executor_follows_the_server() -> None:
    # Live test 2026-10-04: 4 parallel calls at 180 s each timed out on a one-request Ollama.
    judge = build_judge("ragas", ScriptedJudge(), SameVectorEmbedder(), max_workers=1, timeout_s=900)
    assert isinstance(judge, RagasJudge) and (judge.max_workers, judge.timeout_s) == (1, 900)
    settings = Settings(_env_file=None)
    assert (settings.eval_max_workers, settings.eval_timeout_s) == (4, None)
