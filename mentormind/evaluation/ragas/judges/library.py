"""``KNOWHOW_EVAL_JUDGE=ragas``: the four Ragas metrics (spec 09 §3B) computed by the ``ragas`` package.

``ragas.evaluate`` runs ``faithfulness``, ``answer_relevancy`` (``ResponseRelevancy``),
``context_precision`` (``LLMContextPrecisionWithReference``) and ``context_recall`` over the
answered in-scope questions. The judge LLM is the project's ``LLMProvider`` and the embeddings the
local bge-m3 (``adapters``), so DataGuard still sees every judge prompt. ``ragas`` (``eval`` extra)
is imported only when a run starts, so the builtin judge works without it.

A metric ragas cannot compute for a question (unreadable judge answer, timeout) is ``None`` for that
question; ``Judge.score`` counts them in ``failures``.
"""

from __future__ import annotations

import warnings
from collections.abc import Sequence

from mentormind.core.providers.errors import ProviderError
from mentormind.core.providers.llm import LLMProvider
from mentormind.core.schemas import DataClassification
from mentormind.evaluation.ragas.judges.base import Judge, JudgeSample, Scores, TextEmbedder, round_score

#: Ragas metric name -> column of ``ragas_results.csv``.
COLUMNS = {
    "faithfulness": "faithfulness",
    "answer_relevancy": "answer_relevancy",
    "llm_context_precision_with_reference": "context_precision",
    "context_recall": "context_recall",
}


class RagasJudge(Judge):
    kind = "ragas"

    def __init__(
        self, llm: LLMProvider, embedder: TextEmbedder, *, max_workers: int = 4, timeout_s: float = 180
    ) -> None:
        super().__init__(llm, embedder)
        #: Parallel judge calls; keep it at the vLLM server's ``max_num_seqs``.
        self.max_workers = max_workers
        self.timeout_s = timeout_s

    def _score(self, samples: Sequence[JudgeSample], label: DataClassification) -> list[Scores]:
        with warnings.catch_warnings():
            # ragas 0.4 flags its legacy metric imports and ``evaluate`` for 1.0; pinned to 0.4.3.
            warnings.simplefilter("ignore", DeprecationWarning)
            return self._evaluate(samples, label)

    def _evaluate(self, samples: Sequence[JudgeSample], label: DataClassification) -> list[Scores]:
        from ragas import EvaluationDataset, SingleTurnSample, evaluate
        from ragas.dataset_schema import EvaluationResult
        from ragas.metrics import (
            Faithfulness,
            LLMContextPrecisionWithReference,
            LLMContextRecall,
            ResponseRelevancy,
        )
        from ragas.run_config import RunConfig

        from mentormind.evaluation.ragas.judges.adapters import GuardedRagasLLM, ProjectEmbeddings

        llm = GuardedRagasLLM(self.llm, label)
        dataset = EvaluationDataset(
            [
                SingleTurnSample(
                    user_input=s.question,
                    response=s.answer,
                    retrieved_contexts=list(s.contexts),
                    reference=s.ground_truth,
                )
                for s in samples
            ]
        )
        result = evaluate(
            dataset,
            metrics=[Faithfulness(), ResponseRelevancy(), LLMContextPrecisionWithReference(), LLMContextRecall()],
            llm=llm,
            embeddings=ProjectEmbeddings(self.embedder),
            # Retry only what may pass on a second try; a guard refusal must not be retried.
            run_config=RunConfig(
                timeout=round(self.timeout_s),
                max_retries=2,
                max_workers=self.max_workers,
                exception_types=(ProviderError,),
            ),
            raise_exceptions=False,
            show_progress=False,
        )
        if llm.blocked is not None:
            raise llm.blocked
        assert isinstance(result, EvaluationResult)  # return_executor=False
        return [{column: round_score(row.get(name)) for name, column in COLUMNS.items()} for row in result.scores]
