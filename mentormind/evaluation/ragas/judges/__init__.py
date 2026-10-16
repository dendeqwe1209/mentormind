"""Who computes the four Ragas metrics, chosen by ``KNOWHOW_EVAL_JUDGE`` (spec 09 §5b).

``base.Judge`` is the abstract judge (template method ``score``; subclasses register by ``kind``).
``library`` (``ragas``: the ``ragas`` package, its judge LLM plugged in through ``adapters``) and
``builtin`` (``builtin``: the project's own prompts, same definitions, no ragas/langchain) are
the two judges; both call the judge LLM through ``LLMProvider``, so DataGuard, PII masking and
audit apply either way. ``factory.build_judge`` picks one.
"""

import os

# Ragas sends usage analytics to its own server unless told not to; nothing leaves the site. Set
# here, before any module of this package can import ragas.
os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")

from mentormind.evaluation.ragas.judges.base import Judge, JudgeSample, Scores, TextEmbedder  # noqa: E402
from mentormind.evaluation.ragas.judges.builtin import BuiltinJudge  # noqa: E402
from mentormind.evaluation.ragas.judges.factory import JUDGES, JudgeConfigError, build_judge  # noqa: E402
from mentormind.evaluation.ragas.judges.library import RagasJudge  # noqa: E402

__all__ = [
    "JUDGES",
    "BuiltinJudge",
    "Judge",
    "JudgeConfigError",
    "JudgeSample",
    "RagasJudge",
    "Scores",
    "TextEmbedder",
    "build_judge",
]
