"""VLM providers (spec 04 §2): interface, registry, implementations, factory.

Importing this package registers every provider. To add one: implement a :class:`VLMProvider`
subclass in ``backends/``, decorate it with ``@register_vlm("name")`` and import it below. For an
OpenAI-compatible vendor it is only a row in ``mentormind.core.providers.openai_compat.endpoints``
plus a default model id in ``catalog``.
"""

from mentormind.core.providers.vlm.backends import fake, openai_compat
from mentormind.core.providers.vlm.base import VLMProvider
from mentormind.core.providers.vlm.factory import get_vlm_provider, vlm_config_from_settings
from mentormind.core.providers.vlm.models import ImageInput, VLMResponse
from mentormind.core.providers.vlm.registry import VLM_REGISTRY, register_vlm

__all__ = [
    "VLM_REGISTRY",
    "ImageInput",
    "VLMProvider",
    "VLMResponse",
    "fake",
    "get_vlm_provider",
    "openai_compat",
    "register_vlm",
    "vlm_config_from_settings",
]
