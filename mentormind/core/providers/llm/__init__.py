"""LLM providers (spec 06 §2), shared by the VLM passes (spec 04) and the agents (spec 06).

``base`` (interface + outbound guard), ``models``, ``registry``, ``factory``, ``catalog`` (default
model ids), ``context`` (confidential passages never reach the cloud), ``backends/``
(``openai_compat``, ``fake``). Importing this package registers every backend.
"""

from mentormind.core.providers.llm.backends import fake, openai_compat
from mentormind.core.providers.llm.base import LLMProvider
from mentormind.core.providers.llm.context import ContextPassage, filter_passages, strictest
from mentormind.core.providers.llm.factory import get_llm_provider, llm_config_from_settings
from mentormind.core.providers.llm.models import LLMResponse
from mentormind.core.providers.llm.registry import LLM_REGISTRY, register_llm

__all__ = [
    "LLM_REGISTRY",
    "ContextPassage",
    "LLMProvider",
    "LLMResponse",
    "fake",
    "filter_passages",
    "get_llm_provider",
    "llm_config_from_settings",
    "openai_compat",
    "register_llm",
    "strictest",
]
