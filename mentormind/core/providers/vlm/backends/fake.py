"""FakeVLM — deterministic provider for tests and offline demo (spec 04 §2).

Answers from a script: ``responses`` are returned in call order and the last one repeats once
the script runs out. ``from_config`` reads them from ``options["fixture"]``, a JSON file under
``tests/fixtures/vlm/``: a top-level list is a script, anything else is one fixed answer.
Every call is recorded in :attr:`FakeVLM.calls` so tests can assert what would have been sent.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict

from mentormind.core.providers.models import ProviderConfig, TokenUsage
from mentormind.core.providers.transport import HttpClient
from mentormind.core.providers.vlm.base import VLMProvider
from mentormind.core.providers.vlm.models import ImageInput
from mentormind.core.providers.vlm.registry import register_vlm

Scripted = str | Mapping[str, Any]


class FakeCall(BaseModel):
    """What one call would have sent to a real endpoint."""

    model_config = ConfigDict(frozen=True)

    prompt: str
    frames: tuple[Path, ...]
    #: Exactly the bytes a real endpoint would have received (after any face blurring).
    images: tuple[ImageInput, ...]
    json_schema: dict[str, Any] | None
    system: str | None
    temperature: float | None


@register_vlm("fake")
class FakeVLM(VLMProvider):
    def __init__(
        self,
        responses: Sequence[Scripted] = (),
        *,
        name: str = "fake",
        model: str = "fake-vlm",
        is_cloud: bool = False,
    ) -> None:
        self.name = name
        self.model = model
        self.is_cloud = is_cloud
        self._script = [_as_text(r) for r in responses] or ['{"steps": []}']
        self.calls: list[FakeCall] = []

    @classmethod
    def from_config(cls, config: ProviderConfig, http: HttpClient | None = None) -> Self:
        options = config.options
        responses: list[Scripted] = list(options.get("responses", []))
        fixture = options.get("fixture")
        if fixture:
            loaded = json.loads(Path(fixture).read_text(encoding="utf-8"))
            responses = loaded if isinstance(loaded, list) else [loaded]
        return cls(
            responses,
            name=config.provider,
            model=config.model or "fake-vlm",
            is_cloud=bool(options.get("is_cloud", False)),
        )

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
        self.calls.append(
            FakeCall(
                prompt=prompt,
                frames=tuple(image.path for image in images),
                images=tuple(images),
                json_schema=dict(json_schema) if json_schema is not None else None,
                system=system,
                temperature=temperature,
            )
        )
        text = self._script[min(len(self.calls), len(self._script)) - 1]
        usage = TokenUsage(prompt_tokens=len(prompt) + 100 * len(images), completion_tokens=len(text))
        return text, usage


def _as_text(response: Scripted) -> str:
    return response if isinstance(response, str) else json.dumps(response, ensure_ascii=False)
