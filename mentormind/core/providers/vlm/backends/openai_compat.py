"""OpenAI-compatible VLM provider: self-hosted vLLM and every cloud vendor in one class.

Frames are sent as base64 ``image_url`` parts of ONE user message, text first ("the following
images are consecutive frames..."), which every OpenAI-compatible endpoint accepts — including
the self-hosted Qwen3-VL-8B server in ``3rdparty/vlm_server`` (spec 04 §2, FR-08).
"""

from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
from typing import Any, Self

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
from mentormind.core.providers.vlm.base import VLMProvider
from mentormind.core.providers.vlm.catalog import default_vlm_model
from mentormind.core.providers.vlm.models import ImageInput
from mentormind.core.providers.vlm.registry import register_vlm


@register_vlm(*OPENAI_COMPAT_ENDPOINTS, GENERIC_OPENAI_COMPATIBLE)
class OpenAICompatVLM(VLMProvider):
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
        endpoint = resolve_endpoint(config, default_model=default_vlm_model(config.provider), env_prefix="VLM")
        return cls(ChatClient.from_config(endpoint, config, http))

    def _complete(
        self,
        images: Sequence[ImageInput],
        prompt: str,
        *,
        json_schema: Mapping[str, Any] | None,
        system: str | None,
        temperature: float | None,
        max_tokens: int | None,
    ) -> tuple[str, TokenUsage | None]:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        content += [
            {
                "type": "image_url",
                "image_url": {"url": f"data:{image.mime_type};base64," + base64.b64encode(image.data).decode("ascii")},
            }
            for image in images
        ]
        return self._chat.complete(
            content,
            system=system,
            json_schema=json_schema,
            temperature=temperature,
            max_tokens=max_tokens,
        )
