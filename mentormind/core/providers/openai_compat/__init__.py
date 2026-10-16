"""OpenAI-compatible vendors: the endpoint table and the local-vs-cloud test for URLs."""

from mentormind.core.providers.openai_compat.endpoints import (
    GENERIC_OPENAI_COMPATIBLE,
    LOCAL_OPENAI,
    LOCAL_VLM_BASE_URL,
    OPENAI_COMPAT_ENDPOINTS,
    Endpoint,
)
from mentormind.core.providers.openai_compat.locality import is_private_url

__all__ = [
    "GENERIC_OPENAI_COMPATIBLE",
    "LOCAL_OPENAI",
    "LOCAL_VLM_BASE_URL",
    "OPENAI_COMPAT_ENDPOINTS",
    "Endpoint",
    "is_private_url",
]
