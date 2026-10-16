"""The VLM binding of the generic provider registry.

Providers register themselves at import time with :func:`register_vlm`; the package
``__init__`` imports every provider module so the decorators run.
"""

from __future__ import annotations

from collections.abc import Callable

from mentormind.core.providers.registry import ProviderRegistry
from mentormind.core.providers.vlm.base import VLMProvider

VLM_REGISTRY: ProviderRegistry[VLMProvider] = ProviderRegistry("VLM")


def register_vlm(*names: str) -> Callable[[type[VLMProvider]], type[VLMProvider]]:
    """Register a :class:`VLMProvider` subclass under one or more config names."""
    return VLM_REGISTRY.register(*names)
