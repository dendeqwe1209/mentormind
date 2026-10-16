"""The LLM binding of the generic provider registry."""

from __future__ import annotations

from collections.abc import Callable

from mentormind.core.providers.llm.base import LLMProvider
from mentormind.core.providers.registry import ProviderRegistry

LLM_REGISTRY: ProviderRegistry[LLMProvider] = ProviderRegistry("LLM")


def register_llm(*names: str) -> Callable[[type[LLMProvider]], type[LLMProvider]]:
    """Register an :class:`LLMProvider` subclass under one or more config names."""
    return LLM_REGISTRY.register(*names)
