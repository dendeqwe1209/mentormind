"""One ``POST {base_url}/chat/completions`` call, shared by the VLM and LLM kinds."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mentormind.core.providers.errors import ProviderError
from mentormind.core.providers.models import ProviderConfig, TokenUsage
from mentormind.core.providers.openai_compat.resolve import ResolvedEndpoint
from mentormind.core.providers.transport import HttpClient, HttpxClient, RetryPolicy

#: A user message: plain text, or OpenAI content parts (text + image_url).
Content = str | Sequence[Mapping[str, Any]]


class ChatClient:
    """Builds the request body and reads the answer of an OpenAI-compatible endpoint."""

    def __init__(
        self,
        endpoint: ResolvedEndpoint,
        http: HttpClient,
        *,
        max_tokens: int | None = None,
        extra_body: Mapping[str, Any] | None = None,
    ) -> None:
        self.endpoint = endpoint
        self._http = http
        self._max_tokens = max_tokens
        self._extra_body = dict(extra_body or {})

    @classmethod
    def from_config(cls, endpoint: ResolvedEndpoint, config: ProviderConfig, http: HttpClient | None) -> ChatClient:
        transport = http or HttpxClient(timeout_s=config.timeout_s, retry=RetryPolicy(max_retries=config.max_retries))
        return cls(endpoint, transport, max_tokens=config.max_tokens, extra_body=config.extra_body)

    def complete(
        self,
        content: Content,
        *,
        system: str | None = None,
        json_schema: Mapping[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[str, TokenUsage | None]:
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": content if isinstance(content, str) else list(content)})
        # Configured extras first, so the call's own fields always win over them.
        payload: dict[str, Any] = {
            **self._extra_body,
            "model": self.endpoint.model,
            "messages": messages,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if (max_tokens or self._max_tokens) is not None:
            payload["max_tokens"] = max_tokens or self._max_tokens
        response_format = self.response_format(json_schema)
        if response_format is not None:
            payload["response_format"] = response_format
        body = self._http.post_json(f"{self.endpoint.base_url}/chat/completions", payload, headers=self._headers())
        return message_text(body), usage_from(body)

    def response_format(self, json_schema: Mapping[str, Any] | None) -> dict[str, Any] | None:
        mode = self.endpoint.json_mode
        if json_schema is None or mode == "off":
            return None
        if mode == "json_object":
            return {"type": "json_object"}
        return {
            "type": "json_schema",
            "json_schema": {"name": "knowhow_output", "schema": dict(json_schema)},
        }

    def _headers(self) -> dict[str, str]:
        key = self.endpoint.api_key
        return {"Authorization": f"Bearer {key}"} if key else {}


def message_text(body: Mapping[str, Any]) -> str:
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(f"Unexpected chat response shape: {str(body)[:500]}") from exc
    if isinstance(content, str):
        return content
    if content is None:
        # No answer text: a thinking model (vLLM --reasoning-parser) that spent max_tokens reasoning
        # returns content=null. An empty answer, which callers treat as unreadable (spec 04 AC-29).
        return ""
    if isinstance(content, list):  # some vendors return content parts
        return "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    raise ProviderError(f"Unexpected message content type: {type(content).__name__}")


def usage_from(body: Mapping[str, Any]) -> TokenUsage | None:
    usage = body.get("usage")
    if not isinstance(usage, dict):
        return None
    return TokenUsage(
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
    )
