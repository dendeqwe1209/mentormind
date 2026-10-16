"""``Agent`` — what every agent of spec 06 shares: an LLM, its prompts, one trace line per call.

``run`` is a template method: it times the call, lets the subclass answer (``_run``) while an
``AgentRun`` collects every prompt sent and the context shown, then writes the trace (FR-04), so
no agent answers untraced. A new agent: subclass ``Agent[Request, Response]``, set ``kind`` and
``prompts``, implement ``_run`` and send prompts through ``generate``.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Generic, TypeVar

from pydantic import BaseModel

from mentormind.agents.base.context import passage_label
from mentormind.agents.base.prompting import PromptBook
from mentormind.agents.base.tracing import TraceLog
from mentormind.core.providers.llm import LLMProvider, LLMResponse
from mentormind.core.providers.llm.context import ContextPassage, filter_passages
from mentormind.core.schemas import Citation, DataClassification
from mentormind.knowledge_base.retrieval.hybrid import RetrievedContext

RequestT = TypeVar("RequestT", bound=BaseModel)
ResponseT = TypeVar("ResponseT", bound=BaseModel)


@dataclass
class AgentRun:
    """What one call used: every prompt sent to the LLM, the context ids it was shown, and the
    numbers behind the agent's decision (e.g. the Work Assistant's guard scores) for the trace."""

    prompts: list[str] = field(default_factory=list)
    context_ids: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


class Agent(ABC, Generic[RequestT, ResponseT]):
    #: Trace kind: the agent's lines go to ``<trace dir>/<kind>-YYYYMMDD.jsonl``.
    kind: ClassVar[str]
    #: The agent's own ``prompts/*.md``.
    prompts: ClassVar[PromptBook]

    def __init__(self, llm: LLMProvider, *, trace: TraceLog | None = None) -> None:
        self.llm = llm
        self.trace = trace or TraceLog(None)

    def run(self, request: RequestT) -> ResponseT:
        """Answer ``request`` and trace the call (an exception leaves no trace line)."""
        started = time.perf_counter()
        call = AgentRun()
        response = self._run(request, call)
        self.trace.write(
            kind=self.kind,
            request=request,
            context_ids=call.context_ids,
            prompts=call.prompts,
            response=response,
            latency_s=time.perf_counter() - started,
            llm=self.llm.name,
            metrics=call.metrics,
        )
        return response

    @abstractmethod
    def _run(self, request: RequestT, call: AgentRun) -> ResponseT:
        """The agent's own work; record the context it shows in ``call.context_ids``."""

    def generate(
        self, call: AgentRun, prompt: str, *, classification: DataClassification, **kwargs: Any
    ) -> LLMResponse:
        """Send ``prompt`` to the LLM (through its outbound guard) and record it for the trace."""
        call.prompts.append(prompt)
        return self.llm.generate(prompt, classification=classification, **kwargs)

    def allowed_passages(self, context: RetrievedContext) -> list[tuple[ContextPassage, Citation]]:
        """Retrieved passages this agent's LLM may receive, with their citations (constitution art. 2).

        For a cloud LLM, ``factory_confidential`` and unlabelled passages are dropped.
        """
        passages = [
            ContextPassage(ref_id=c.ref_id, text=text, classification=passage_label(context, i))
            for i, (text, c) in enumerate(zip(context.passages, context.citations, strict=True))
        ]
        kept = {id(p) for p in filter_passages(passages, self.llm)}
        return [(p, c) for p, c in zip(passages, context.citations, strict=True) if id(p) in kept]
