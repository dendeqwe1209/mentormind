"""The ``ragas`` package plugged into the project's own LLM provider and embedder.

Ragas would otherwise call the LLM with its own client and skip DataGuard, PII masking and the audit
log (constitution art. 2). ``GuardedRagasLLM`` sends every judge prompt through ``LLMProvider``
with the data label of the run; ``ProjectEmbeddings`` uses the Work Assistant's embedder (``KNOWHOW_EMBEDDER``).
"""

from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.outputs import Generation, LLMResult
from langchain_core.prompt_values import PromptValue
from ragas.embeddings import BaseRagasEmbeddings
from ragas.llms import BaseRagasLLM

from mentormind.core.guard import ConfidentialDataError
from mentormind.core.providers.llm import LLMProvider
from mentormind.core.schemas import DataClassification
from mentormind.evaluation.ragas.judges.base import TextEmbedder


class GuardedRagasLLM(BaseRagasLLM):
    """Ragas' judge LLM = the project's ``LLMProvider``, called with the run's data label.

    A prompt DataGuard refuses is remembered in ``blocked``: ragas retries and swallows errors,
    so the judge re-raises it after the run instead of reporting empty scores.
    """

    def __init__(self, llm: LLMProvider, classification: DataClassification) -> None:
        super().__init__()
        self.llm = llm
        self.classification = classification
        self.blocked: ConfidentialDataError | None = None

    def generate_text(
        self,
        prompt: PromptValue,
        n: int = 1,
        temperature: float | None = 0.01,
        stop: list[str] | None = None,
        callbacks: Any = None,
    ) -> LLMResult:
        texts = []
        for _ in range(n):
            try:
                response = self.llm.generate(
                    prompt.to_string(), classification=self.classification, temperature=temperature
                )
            except ConfidentialDataError as exc:
                self.blocked = exc
                raise
            texts.append(response.text)
        return LLMResult(generations=[[Generation(text=text) for text in texts]])

    async def agenerate_text(
        self,
        prompt: PromptValue,
        n: int = 1,
        temperature: float | None = 0.01,
        stop: list[str] | None = None,
        callbacks: Any = None,
    ) -> LLMResult:
        return await asyncio.to_thread(self.generate_text, prompt, n, temperature, stop, callbacks)

    def is_finished(self, response: LLMResult) -> bool:
        return True


class ProjectEmbeddings(BaseRagasEmbeddings):
    """Ragas' embeddings (``answer_relevancy``) = the Work Assistant's embedder (local or remote bge-m3)."""

    def __init__(self, embedder: TextEmbedder) -> None:
        super().__init__()
        self.embedder = embedder

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embedder.embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return self.embedder.embed([text])[0]

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self.embed_documents, texts)

    async def aembed_query(self, text: str) -> list[float]:
        return await asyncio.to_thread(self.embed_query, text)
