"""``build_judge`` — the judge named by ``KNOWHOW_EVAL_JUDGE`` (spec 09 §5b)."""

from __future__ import annotations

from importlib.util import find_spec

from mentormind.core.providers.llm import LLMProvider
from mentormind.evaluation.ragas.judges import builtin, library  # noqa: F401  (defining them registers them)
from mentormind.evaluation.ragas.judges.base import Judge, TextEmbedder

#: ``KNOWHOW_EVAL_JUDGE`` value -> judge class.
JUDGES = Judge.registry


class JudgeConfigError(RuntimeError):
    """Unknown judge name, or the ``ragas`` judge without the ``eval`` extra installed."""


def build_judge(
    name: str,
    llm: LLMProvider,
    embedder: TextEmbedder,
    *,
    max_workers: int = 4,
    timeout_s: float = 180,
) -> Judge:
    """``max_workers``/``timeout_s`` tune the ragas package's own executor (the builtin judge is sequential)."""
    cls = JUDGES.get(name)
    if cls is None:
        raise JudgeConfigError(
            f"KNOWHOW_EVAL_JUDGE={name!r} không hợp lệ; chọn một trong: {', '.join(sorted(JUDGES))}."
        )
    if cls is library.RagasJudge and find_spec("ragas") is None:
        raise JudgeConfigError(
            "KNOWHOW_EVAL_JUDGE=ragas cần thư viện ragas: uv sync --extra eval (hoặc đặt KNOWHOW_EVAL_JUDGE=builtin)."
        )
    if cls is library.RagasJudge:
        return library.RagasJudge(llm, embedder, max_workers=max_workers, timeout_s=timeout_s)
    return cls(llm, embedder)
