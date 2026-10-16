"""Provider error types shared by every provider kind."""

from __future__ import annotations


class ProviderError(RuntimeError):
    """A provider call failed (network, HTTP status, unexpected response).

    ``status_code`` carries the upstream HTTP status when there was one, so callers can tell a
    quota/transient failure (429/5xx) from a wiring bug without parsing the message.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ProviderConfigError(ProviderError):
    """A provider cannot be built: unknown name, missing API key, missing base URL..."""


class InvalidJSONError(ProviderError):
    """The model answered, but not with a JSON object. ``raw_text`` keeps the answer for repair."""

    def __init__(self, message: str, *, raw_text: str) -> None:
        super().__init__(message)
        self.raw_text = raw_text
