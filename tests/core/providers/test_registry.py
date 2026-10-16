"""The generic provider registry: names, rebinding, construction."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Self

import pytest

from mentormind.core.providers.models import ProviderConfig, TokenUsage
from mentormind.core.providers.registry import ProviderRegistry
from mentormind.core.providers.transport import HttpClient
from mentormind.core.providers.vlm import VLMProvider
from mentormind.core.providers.vlm.backends.fake import FakeVLM
from mentormind.core.providers.vlm.backends.openai_compat import OpenAICompatVLM
from mentormind.core.providers.vlm.models import ImageInput


def test_ac_11_new_provider_needs_only_a_class_and_a_name(frames: list[Path]) -> None:
    registry: ProviderRegistry[VLMProvider] = ProviderRegistry("VLM")

    @registry.register("echo", "echo_alias")
    class EchoVLM(VLMProvider):
        def __init__(self, name: str) -> None:
            self.name, self.model, self.is_cloud = name, "echo-1", False

        @classmethod
        def from_config(cls, config: ProviderConfig, http: HttpClient | None = None) -> Self:
            return cls(config.provider)

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
            return json.dumps({"frames": len(images)}), None

    vlm = registry.create(ProviderConfig(provider="echo_alias"))
    assert vlm.name == "echo_alias"
    assert vlm.generate_json(frames, "p", {}, classification="synthetic") == {"frames": 3}


def test_registry_refuses_rebinding_a_name_to_another_class() -> None:
    registry: ProviderRegistry[VLMProvider] = ProviderRegistry("VLM")
    registry.register("x")(FakeVLM)
    registry.register("x")(FakeVLM)  # same class: no-op
    with pytest.raises(ValueError, match="already registered"):
        registry.register("x")(OpenAICompatVLM)
