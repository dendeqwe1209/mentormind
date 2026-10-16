"""Scripted judge and assistant for the evaluation tests."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from mentormind.core.providers.llm.backends.fake import FakeLLM
from mentormind.core.providers.models import TokenUsage
from mentormind.core.schemas import Citation
from mentormind.core.schemas.agents import AskRequest, AssistantAnswer

#: (marker of a judge prompt, JSON the judge answers): the ragas package's prompts, then the builtin
#: judge's. Both sets give faithfulness 3/4, context precision 1, context recall 1.
RAGAS_ANSWERS: list[tuple[str, dict[str, Any]]] = [
    (
        "judge the faithfulness of a series of statements",
        {
            "statements": [
                {"statement": s, "reason": "r", "verdict": v} for s, v in (("a", 1), ("b", 1), ("c", 0), ("d", 1))
            ]
        },
    ),
    ("analyze the complexity of each sentence", {"statements": ["a", "b", "c", "d"]}),
    ("Generate a question for the given answer", {"question": "q", "noncommittal": 0}),
    ("verify if the context was useful", {"reason": "r", "verdict": 1}),
    (
        "classify if the sentence can be attributed",
        {"classifications": [{"statement": "s", "reason": "r", "attributed": 1}]},
    ),
    (
        "[faithfulness]",
        {"claims": [{"claim": c, "supported": v} for c, v in (("a", True), ("b", True), ("c", False), ("d", True))]},
    ),
    ("[answer_relevancy]", {"questions": ["q1", "q2", "q3"], "noncommittal": False}),
    ("[context_precision]", {"verdicts": [True]}),
    ("[context_recall]", {"sentences": [{"sentence": "s", "attributed": True}]}),
]


class ScriptedJudge(FakeLLM):
    """Answers each metric prompt (either judge) with the fixed JSON of ``RAGAS_ANSWERS``."""

    def _complete(
        self,
        prompt: str,
        *,
        system: str | None,
        json_schema: Mapping[str, Any] | None,
        temperature: float | None,
        max_tokens: int | None,
    ) -> tuple[str, TokenUsage | None]:
        super()._complete(
            prompt,
            system=system,
            json_schema=json_schema,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        answer = next(answer for marker, answer in RAGAS_ANSWERS if marker in prompt)
        return json.dumps(answer, ensure_ascii=False), None


class SameVectorEmbedder:
    """Every text gets the same vector: any generated question is as similar as can be (1.0)."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]


def cite(*refs: str) -> list[Citation]:
    return [Citation(source_type="work_profile", ref_id=r, snippet=f"nội dung {r}", score=0.8) for r in refs]


class ScriptedAssistant:
    """Per-qid answers keyed by question text."""

    def __init__(self, answers: Mapping[str, AssistantAnswer]) -> None:
        self.answers = answers
        self.asked: list[AskRequest] = []

    def ask(self, request: AskRequest) -> AssistantAnswer:
        self.asked.append(request)
        return self.answers[request.question]


def answered(text: str, refs: Sequence[str]) -> AssistantAnswer:
    return AssistantAnswer(answer=text, citations=cite(*refs), confidence=0.8, refused=False)


REFUSED = AssistantAnswer(answer="Chưa có thông tin.", confidence=0.0, refused=True)
