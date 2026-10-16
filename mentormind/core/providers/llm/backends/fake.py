"""FakeLLM — scripted answers for tests; records every prompt it would have sent."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Self

from pydantic import BaseModel, ConfigDict

from mentormind.core.providers.llm.base import LLMProvider
from mentormind.core.providers.llm.registry import register_llm
from mentormind.core.providers.models import ProviderConfig, TokenUsage
from mentormind.core.providers.transport import HttpClient

Scripted = str | Mapping[str, Any]


class FakeLLMCall(BaseModel):
    model_config = ConfigDict(frozen=True)

    prompt: str
    system: str | None
    json_schema: dict[str, Any] | None
    temperature: float | None


@register_llm("fake")
class FakeLLM(LLMProvider):
    def __init__(
        self,
        responses: Sequence[Scripted] = (),
        *,
        name: str = "fake",
        model: str = "fake-llm",
        is_cloud: bool = False,
    ) -> None:
        self.name = name
        self.model = model
        self.is_cloud = is_cloud
        self._script = [_as_text(r) for r in responses] or ["{}"]
        self.calls: list[FakeLLMCall] = []

    @classmethod
    def from_config(cls, config: ProviderConfig, http: HttpClient | None = None) -> Self:
        return cls(
            list(config.options.get("responses", [])),
            name=config.provider,
            model=config.model or "fake-llm",
            is_cloud=bool(config.options.get("is_cloud", False)),
        )

    def _complete(
        self,
        prompt: str,
        *,
        system: str | None,
        json_schema: Mapping[str, Any] | None,
        temperature: float | None,
        max_tokens: int | None,
    ) -> tuple[str, TokenUsage | None]:
        self.calls.append(
            FakeLLMCall(
                prompt=prompt,
                system=system,
                json_schema=dict(json_schema) if json_schema is not None else None,
                temperature=temperature,
            )
        )
        text = self._script[min(len(self.calls), len(self._script)) - 1]
        return text, TokenUsage(prompt_tokens=len(prompt), completion_tokens=len(text))


def _as_text(response: Scripted) -> str:
    return response if isinstance(response, str) else json.dumps(response, ensure_ascii=False)
