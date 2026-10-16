"""OpenAI-compatible LLM provider: the self-hosted server and every cloud vendor in one class."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self

from mentormind.core.providers.llm.base import LLMProvider
from mentormind.core.providers.llm.catalog import default_llm_model
from mentormind.core.providers.llm.registry import register_llm
from mentormind.core.providers.models import ProviderConfig, TokenUsage
from mentormind.core.providers.openai_compat import (
    GENERIC_OPENAI_COMPATIBLE,
    OPENAI_COMPAT_ENDPOINTS,
)
from mentormind.core.providers.openai_compat.chat import ChatClient
from mentormind.core.providers.openai_compat.resolve import (
    api_key_env_for,
    base_url_env_for,
    resolve_endpoint,
)
from mentormind.core.providers.transport import HttpClient


@register_llm(*OPENAI_COMPAT_ENDPOINTS, GENERIC_OPENAI_COMPATIBLE)
class OpenAICompatLLM(LLMProvider):
    def __init__(self, chat: ChatClient) -> None:
        self.name = chat.endpoint.name
        self.model = chat.endpoint.model
        self.is_cloud = chat.endpoint.is_cloud
        self._chat = chat

    @classmethod
    def api_key_env(cls, name: str) -> str | None:
        return api_key_env_for(name)

    @classmethod
    def base_url_env(cls, name: str) -> str | None:
        return base_url_env_for(name)

    @classmethod
    def from_config(cls, config: ProviderConfig, http: HttpClient | None = None) -> Self:
        endpoint = resolve_endpoint(config, default_model=default_llm_model(config.provider), env_prefix="LLM")
        return cls(ChatClient.from_config(endpoint, config, http))

    def _complete(
        self,
        prompt: str,
        *,
        system: str | None,
        json_schema: Mapping[str, Any] | None,
        temperature: float | None,
        max_tokens: int | None,
    ) -> tuple[str, TokenUsage | None]:
        return self._chat.complete(
            prompt,
            system=system,
            json_schema=json_schema,
            temperature=temperature,
            max_tokens=max_tokens,
        )
