"""LLM provider interface (spec 06 §2): text in, text or JSON out.

Shared by the VLM passes that need plain text (spec 04 pass C, propose-reasons) and the agents
(spec 06). Like the VLM kind, :meth:`LLMProvider.generate` is a template method no provider can
bypass: DataGuard first, then for a cloud provider PII masking, LeakGuard and audit (spec 01
FR-09b), then the subclass's :meth:`LLMProvider._complete`, then the answer's tokens restored.
"""

from __future__ import annotations

import time
from abc import abstractmethod
from collections.abc import Mapping
from typing import Any, ClassVar

from mentormind.core.guard import GuardPolicy, OutboundSession
from mentormind.core.providers.base import ProviderBase
from mentormind.core.providers.llm.models import LLMResponse
from mentormind.core.providers.models import TokenUsage
from mentormind.core.providers.parsing import parse_json_object
from mentormind.core.schemas.common import DataClassification


class LLMProvider(ProviderBase):
    """Generates text. Subclass, then ``@register_llm("name")``."""

    kind: ClassVar[str] = "LLM"

    #: Model id sent to the endpoint.
    model: str
    #: Outbound guard for cloud calls; ``get_llm_provider`` sets it from ``KNOWHOW_GUARD_*``.
    guard_policy: GuardPolicy = GuardPolicy()

    def generate(
        self,
        prompt: str,
        *,
        classification: DataClassification | str,
        system: str | None = None,
        json_schema: Mapping[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Send ``prompt``; ``classification`` is the strictest label of the data inside it.

        Raises:
            ConfidentialDataError: factory_confidential data and a cloud provider.
            SensitiveDataLeakError: a cloud call would still carry PII after masking.
            ProviderError: transport/HTTP failure or unexpected response shape.
        """
        session = OutboundSession(self.guard_policy, self, classification, kind=self.kind, model=self.model)
        outgoing_prompt = session.mask(prompt) or ""
        outgoing_system = session.mask(system)
        session.ensure_clean([outgoing_prompt, outgoing_system])
        started = time.perf_counter()
        text, usage = self._complete(
            outgoing_prompt,
            system=outgoing_system,
            json_schema=json_schema,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        latency = time.perf_counter() - started
        session.audit(duration_ms=round(latency * 1000))
        return LLMResponse(
            text=session.restore(text),
            usage=usage,
            latency_s=latency,
            provider=self.name,
            model=self.model,
        )

    def generate_text(self, prompt: str, *, classification: DataClassification | str, **kwargs: Any) -> str:
        return self.generate(prompt, classification=classification, **kwargs).text

    def generate_json(
        self,
        prompt: str,
        json_schema: Mapping[str, Any],
        *,
        classification: DataClassification | str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Like :meth:`generate`, parsed as a JSON object (raises ``InvalidJSONError``)."""
        response = self.generate(prompt, classification=classification, json_schema=json_schema, **kwargs)
        return parse_json_object(response.text)

    @abstractmethod
    def _complete(
        self,
        prompt: str,
        *,
        system: str | None,
        json_schema: Mapping[str, Any] | None,
        temperature: float | None,
        max_tokens: int | None,
    ) -> tuple[str, TokenUsage | None]:
        """Call the model once; return its text and token usage (None when unreported)."""
