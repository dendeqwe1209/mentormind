"""Work Assistant (spec 06 §3): a new worker asks about a step, gets a grounded answer or a refusal.

Retrieve (spec 05 ``HybridRetriever``) and keep the passages the LLM may receive (constitution
art. 2), then three guards in order; the first that blocks ends the call with the standard refusal
and the expert with the most contributions to the process:

1. RRF floor — no passage, or the best spec 05 score below ``KNOWHOW_ASSIST_MIN_SCORE``. That score
   is Reciprocal Rank Fusion (rank only, at most ~0.133), so this only stops "nothing found".
2. Cosine gate — the question and the passages embedded with spec 05's bge-m3; the best cosine
   below ``KNOWHOW_ASSIST_MIN_COSINE`` refuses an off-topic question without calling the LLM.
3. LLM JSON — ``{"answerable", "answer", "used_sources"}`` forced by ``json_schema``.
   ``answerable=false`` refuses. Post-check (art. 4: no answer without a source): ``used_sources``
   not empty, inside 1..N, and exactly the [n] markers of ``answer``; otherwise ask once more,
   then refuse.

``confidence`` = mean cosine of the passages in ``used_sources``. The trace records ``max_rrf``,
``max_cosine`` and which guard blocked (``blocked_by``).
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from mentormind.agents.base import Agent, AgentRun, PromptBook, TraceLog
from mentormind.agents.ports import Embedder, ExpertDirectory, Retriever
from mentormind.core.providers.errors import InvalidJSONError
from mentormind.core.providers.llm import LLMProvider, strictest
from mentormind.core.providers.llm.context import ContextPassage
from mentormind.core.providers.parsing import parse_json_object
from mentormind.core.schemas import Citation
from mentormind.core.schemas.agents import AskRequest, AssistantAnswer
from mentormind.knowledge_base.retrieval.hybrid import RetrievedContext

#: Guard 1: spec 05 RRF score (rank based, ~0.133 at most): ~ "nothing near the top of a ranking".
DEFAULT_MIN_SCORE = 0.02
#: Guard 2: bge-m3 cosine between the question and the best passage. Tuned on the LASI golden set
#: (2026-10-04): every on-topic question >= 0.435, 3 of 5 off-topic ones below 0.40.
DEFAULT_MIN_COSINE = 0.40
REFUSAL = (
    "Mình chưa có thông tin đã được chuyên gia duyệt để trả lời câu này, nên không trả lời để tránh hướng dẫn sai."
)
RETRY_NOTE = (
    "\n\nLƯU Ý: câu trả lời trước không hợp lệ (JSON sai, hoặc marker [n] trong answer không trùng "
    "used_sources, hoặc dùng số ngoài 1..{n}). Trả lại đúng JSON theo quy tắc."
)
ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answerable": {"type": "boolean"},
        "answer": {"type": "string"},
        "used_sources": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["answerable", "answer", "used_sources"],
}
_MARKER = re.compile(r"\[(\d+)\]")

Source = tuple[ContextPassage, Citation]


class _Reply(BaseModel):
    answerable: bool
    answer: str = ""
    used_sources: list[int] = []


class WorkAssistant(Agent[AskRequest, AssistantAnswer]):
    kind = "ask"
    prompts = PromptBook(Path(__file__).resolve().parent / "prompts")

    def __init__(
        self,
        retriever: Retriever,
        llm: LLMProvider,
        *,
        embedder: Embedder,
        experts: ExpertDirectory | None = None,
        min_score: float = DEFAULT_MIN_SCORE,
        min_cosine: float = DEFAULT_MIN_COSINE,
        trace: TraceLog | None = None,
    ) -> None:
        super().__init__(llm, trace=trace)
        self.retriever = retriever
        self.embedder = embedder
        self.experts = experts
        self.min_score = min_score
        self.min_cosine = min_cosine

    def ask(self, request: AskRequest) -> AssistantAnswer:
        """Answer ``request`` from retrieved context only, or refuse (spec 06 FR-01)."""
        return self.run(request)

    def _run(self, request: AskRequest, call: AgentRun) -> AssistantAnswer:
        context = self.retriever.retrieve(request.question, request.process_id)
        sources = self.allowed_passages(context)
        call.context_ids = [c.ref_id for _, c in sources]
        best_rrf = max((c.score or 0.0 for _, c in sources), default=0.0)
        call.metrics["max_rrf"] = round(best_rrf, 4)
        if not sources or best_rrf < self.min_score:
            return self._refuse(request, call, "rrf")
        cosines = self._cosines(request.question, sources)
        call.metrics["max_cosine"] = round(max(cosines), 3)
        if max(cosines) < self.min_cosine:
            return self._refuse(request, call, "cosine")
        return self._answer(request, context, sources, cosines, call)

    def _cosines(self, question: str, sources: Sequence[Source]) -> list[float]:
        """bge-m3 cosine between the question and each passage, in source order."""
        asked, *passages = self.embedder.embed([question, *(p.text for p, _ in sources)])
        return [_cosine(asked, passage) for passage in passages]

    def _answer(
        self,
        request: AskRequest,
        context: RetrievedContext,
        sources: Sequence[Source],
        cosines: Sequence[float],
        call: AgentRun,
    ) -> AssistantAnswer:
        prompt = self.prompts.render(
            "assistant.md",
            process_id=request.process_id or "(chưa rõ)",
            sources="\n".join(f"[{i}] ({c.ref_id}) {p.text}" for i, (p, c) in enumerate(sources, start=1)),
            facts=self._facts(context),
            question=request.question,
        )
        label = strictest(p.classification for p, _ in sources)
        for attempt in range(2):
            text_prompt = prompt if attempt == 0 else prompt + RETRY_NOTE.format(n=len(sources))
            response = self.generate(
                call, text_prompt, classification=label, json_schema=ANSWER_SCHEMA, temperature=0.2
            )
            try:
                reply = _Reply.model_validate(parse_json_object(response.text))
            except (InvalidJSONError, ValidationError):
                continue
            if not reply.answerable:
                return self._refuse(request, call, "llm_unanswerable")
            used = set(reply.used_sources)
            if used and used <= set(range(1, len(sources) + 1)) and _markers(reply.answer) == used:
                confidence = sum(cosines[n - 1] for n in used) / len(used)
                call.metrics["blocked_by"] = None
                return AssistantAnswer(
                    answer=reply.answer.strip(),
                    citations=[c for _, c in sources],
                    confidence=round(confidence, 3),
                    refused=False,
                )
        return self._refuse(request, call, "post_check")

    def _facts(self, context: RetrievedContext) -> str:
        # Graph facts carry no label of their own: only a self-hosted LLM receives them.
        if self.llm.is_cloud or not context.graph_facts:
            return ""
        return "Thông tin quan hệ (tham khảo, không đánh số):\n" + "\n".join(
            f"- {fact}" for fact in context.graph_facts
        )

    def _refuse(self, request: AskRequest, call: AgentRun, blocked_by: str) -> AssistantAnswer:
        call.metrics["blocked_by"] = blocked_by
        contact = None
        if self.experts is not None and request.process_id:
            contact = self.experts.top_contributor(request.process_id)
        return AssistantAnswer(answer=REFUSAL, citations=[], confidence=0.0, refused=True, suggested_contact=contact)


def _markers(text: str) -> set[int]:
    return {int(n) for n in _MARKER.findall(text)}


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / norm if norm else 0.0
