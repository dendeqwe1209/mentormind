"""PiiMasker — replace sensitive values in text with vault tokens (bankassist ``PiiMasker``).

Two detection sources: **known values** (entity-driven: expert or operator names we already know
are sensitive, replaced wherever they appear) and the free-text **recognizers**.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence

from mentormind.core.guard.pii.recognizers import (
    DEFAULT_RECOGNIZERS,
    Recognizer,
    custom_recognizers,
)
from mentormind.core.guard.pii.vault import PiiVault


class PiiMasker:
    """Replaces sensitive values in text with vault tokens."""

    def __init__(
        self,
        vault: PiiVault | None = None,
        *,
        known: Mapping[str, Iterable[str]] | None = None,
        recognizers: Sequence[Recognizer] = DEFAULT_RECOGNIZERS,
        extra_patterns: Mapping[str, str] | None = None,
    ) -> None:
        self.vault = vault or PiiVault()
        self._recognizers = tuple(recognizers) + custom_recognizers(extra_patterns or {})
        # Longest first so "Nguyễn Văn An" wins over "An".
        self._known = sorted(
            ((entity, value) for entity, values in (known or {}).items() for value in values if value),
            key=lambda item: len(item[1]),
            reverse=True,
        )

    def mask_field(self, value: str | None, entity: str) -> str:
        """Structured field: the whole value is the entity (bankassist ``MaskField``)."""
        if value is None or not value.strip():
            return value or ""
        return self.vault.tokenize(value, entity)

    def mask_text(self, text: str | None) -> str:
        """Free text: mask known values, then every recognizer, in priority order."""
        if text is None or not text.strip():
            return text or ""
        result = text
        for entity, value in self._known:
            pattern = re.compile(re.escape(value), re.IGNORECASE)
            if pattern.search(result):
                result = pattern.sub(self.vault.tokenize(value, entity).replace("\\", r"\\"), result)
        for recognizer in self._recognizers:
            spans = sorted(recognizer.find(result))
            # Number tokens in reading order, then splice right-to-left so offsets stay valid.
            tokens = [self.vault.tokenize(result[s:e], recognizer.entity) for s, e in spans]
            for (start, end), token in reversed(list(zip(spans, tokens, strict=True))):
                result = result[:start] + token + result[end:]
        return result

    @property
    def recognizers(self) -> tuple[Recognizer, ...]:
        return self._recognizers
