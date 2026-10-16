"""One generic name -> class registry, instantiated once per provider kind.

Mirrors the omnia provider registry: a read-only mapping that also owns registration and
construction. ``VLM_REGISTRY`` (spec 04) is the first instance; spec 06's LLM kind gets the
whole surface for one line.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from typing import Generic, TypeVar

from mentormind.core.providers.base import ProviderBase
from mentormind.core.providers.errors import ProviderConfigError
from mentormind.core.providers.models import ProviderConfig
from mentormind.core.providers.transport.http import HttpClient

P = TypeVar("P", bound=ProviderBase)


class ProviderRegistry(Mapping[str, type[P]], Generic[P]):
    """Name -> provider class for ONE kind, plus registration and construction."""

    def __init__(self, kind: str) -> None:
        self._kind = kind
        self._classes: dict[str, type[P]] = {}

    def __getitem__(self, name: str) -> type[P]:
        return self._classes[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self._classes)

    def __len__(self) -> int:
        return len(self._classes)

    def register(self, *names: str) -> Callable[[type[P]], type[P]]:
        """Class decorator registering a provider under one or more config names.

        One class may serve several names (the OpenAI-compatible family: every vendor that
        speaks ``/chat/completions`` is a name, not a class).

        Raises:
            ValueError: no name, an empty name, or a name already bound to another class.
        """
        if not names or any(not n for n in names):
            raise ValueError(f"{self._kind} provider registration needs non-empty names")

        def decorator(cls: type[P]) -> type[P]:
            for name in names:
                existing = self._classes.get(name)
                if existing is not None and existing is not cls:
                    raise ValueError(f"{self._kind} provider {name!r} already registered to {existing.__name__}")
                self._classes[name] = cls
            return cls

        return decorator

    def names(self) -> list[str]:
        """Registered names, sorted (stable for CLI output and test ids)."""
        return sorted(self._classes)

    def create(self, config: ProviderConfig, http: HttpClient | None = None) -> P:
        """Build the provider named by ``config.provider``.

        Raises:
            ProviderConfigError: unknown name — never silently falls back to another provider.
        """
        cls = self._classes.get(config.provider)
        if cls is None:
            raise ProviderConfigError(
                f"Provider {self._kind} '{config.provider}' chưa được đăng ký. "
                f"Các provider có sẵn: {', '.join(self.names())}"
            )
        return cls.from_config(config, http)
