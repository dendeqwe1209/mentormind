"""``KNOWHOW_EVAL_JUDGE=builtin``: the four Ragas metrics with the project's own prompts.

Same definitions as the ``ragas`` package (spec 09 §3B), without ragas or langchain:

* ``faithfulness``      claims of the answer supported by the contexts / all claims
* ``answer_relevancy``  mean cosine similarity (embedder) between the question and questions
                        regenerated from the answer; 0 when the answer is noncommittal
* ``context_precision`` average precision of the contexts' usefulness for the ground truth, in rank
                        order (useful contexts ranked first score higher)
* ``context_recall``    sentences of the ground truth found in the contexts / all sentences

One call per metric and question, Vietnamese prompts in ``prompts/``, the JSON shape enforced by the
endpoint's ``response_format``. Every call goes through ``LLMProvider`` (DataGuard, PII masking,
audit); a guard refusal stops the run. A metric the judge cannot answer (bad JSON, provider error
after retries) is ``None`` for that question; ``Judge.score`` counts them in ``failures``.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from mentormind.core.providers.errors import ProviderError
from mentormind.core.schemas import DataClassification
from mentormind.evaluation.ragas.judges.base import Judge, JudgeSample, Scores, round_score

log = logging.getLogger(__name__)
PROMPTS = Path(__file__).resolve().parent / "prompts"

_BOOL = {"type": "boolean"}
_STR = {"type": "string"}


def _object(**properties: Mapping[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": list(properties)}


def _list(items: Mapping[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": dict(items)}


#: Prompt name -> JSON schema of the judge's answer.
SCHEMAS: dict[str, dict[str, Any]] = {
    "faithfulness": _object(claims=_list(_object(claim=_STR, supported=_BOOL))),
    "answer_relevancy": _object(questions=_list(_STR), noncommittal=_BOOL),
    "context_precision": _object(verdicts=_list(_BOOL)),
    "context_recall": _object(sentences=_list(_object(sentence=_STR, attributed=_BOOL))),
}


class BuiltinJudge(Judge):
    kind = "builtin"

    def _score(self, samples: Sequence[JudgeSample], label: DataClassification) -> list[Scores]:
        return [self._score_one(sample, label) for sample in samples]

    def _score_one(self, s: JudgeSample, label: DataClassification) -> Scores:
        return {
            "faithfulness": round_score(self._faithfulness(s, label)),
            "answer_relevancy": round_score(self._answer_relevancy(s, label)),
            "context_precision": round_score(self._context_precision(s, label)),
            "context_recall": round_score(self._context_recall(s, label)),
        }

    def _faithfulness(self, s: JudgeSample, label: DataClassification) -> float | None:
        data = self._ask("faithfulness", label, contexts=_numbered(s.contexts), answer=s.answer)
        claims = [c for c in (data or {}).get("claims", []) if isinstance(c, dict)]
        if not claims:
            return None
        return sum(bool(c.get("supported")) for c in claims) / len(claims)

    def _answer_relevancy(self, s: JudgeSample, label: DataClassification) -> float | None:
        data = self._ask("answer_relevancy", label, question=s.question, answer=s.answer)
        if data is None:
            return None
        if data.get("noncommittal"):
            return 0.0
        generated = [q for q in data.get("questions", []) if isinstance(q, str) and q.strip()]
        if not generated:
            return None
        original, *others = self.embedder.embed([s.question, *generated])
        return sum(_cosine(original, other) for other in others) / len(others)

    def _context_precision(self, s: JudgeSample, label: DataClassification) -> float | None:
        if not s.contexts:
            return None
        data = self._ask(
            "context_precision",
            label,
            question=s.question,
            ground_truth=s.ground_truth,
            contexts=_numbered(s.contexts),
            n=len(s.contexts),
        )
        verdicts = [bool(v) for v in (data or {}).get("verdicts", [])][: len(s.contexts)]
        if not verdicts or not any(verdicts):
            return 0.0 if verdicts else None
        hits, total = 0, 0.0
        for rank, useful in enumerate(verdicts, start=1):
            if useful:
                hits += 1
                total += hits / rank
        return total / hits

    def _context_recall(self, s: JudgeSample, label: DataClassification) -> float | None:
        data = self._ask("context_recall", label, ground_truth=s.ground_truth, contexts=_numbered(s.contexts))
        sentences = [x for x in (data or {}).get("sentences", []) if isinstance(x, dict)]
        if not sentences:
            return None
        return sum(bool(x.get("attributed")) for x in sentences) / len(sentences)

    def _ask(self, metric: str, label: DataClassification, **values: Any) -> dict[str, Any] | None:
        prompt = (PROMPTS / f"{metric}.md").read_text(encoding="utf-8").format(**values)
        try:
            return self.llm.generate_json(prompt, SCHEMAS[metric], classification=label, temperature=0.0)
        except ProviderError as exc:  # bad JSON, HTTP/transport failure after retries
            log.warning("builtin judge: %s not computed: %s", metric, exc)
            return None


def _numbered(contexts: Sequence[str]) -> str:
    return "\n".join(f"[{i}] {c}" for i, c in enumerate(contexts, start=1)) or "(không có)"


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / norm if norm else 0.0
