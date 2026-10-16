"""Data models of the provider layer: how a provider is configured, what a call cost."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from mentormind.core.config import JsonMode


class ProviderConfig(BaseModel):
    """Everything needed to build one provider; ``provider`` selects the registered class."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    model: str | None = None
    base_url: str | None = None
    api_key: SecretStr | None = None
    timeout_s: float = 90.0
    max_retries: int = 3
    json_mode: JsonMode = "auto"
    max_tokens: int | None = None
    #: Hostnames declared local (``KNOWHOW_LOCAL_HOSTS``); only URL-judged endpoints use them.
    local_hosts: tuple[str, ...] = ()
    #: Extra request-body fields for the endpoint (sampling knobs); never overrides the call's own.
    extra_body: dict[str, Any] = Field(default_factory=dict)
    # Provider-specific knobs that do not deserve a first-class field (e.g. FakeVLM fixtures).
    options: dict[str, Any] = Field(default_factory=dict)


class TokenUsage(BaseModel):
    """Token counts of one call as reported by the endpoint."""

    model_config = ConfigDict(frozen=True)

    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens
