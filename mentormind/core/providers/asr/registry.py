"""The ASR binding of the generic provider registry."""

from __future__ import annotations

from collections.abc import Callable

from mentormind.core.providers.asr.base import ASRProvider
from mentormind.core.providers.registry import ProviderRegistry

ASR_REGISTRY: ProviderRegistry[ASRProvider] = ProviderRegistry("ASR")


def register_asr(*names: str) -> Callable[[type[ASRProvider]], type[ASRProvider]]:
    """Register an :class:`ASRProvider` subclass under one or more config names."""
    return ASR_REGISTRY.register(*names)
