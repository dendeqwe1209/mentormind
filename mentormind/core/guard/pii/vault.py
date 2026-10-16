"""Token <-> real value map of one masking session (bankassist-mcp Vault, in memory).

Invariant: within one vault the same real value always gets the same ``[TYPE_n]`` token, so the
model sees consistent placeholders; :meth:`PiiVault.restore` puts the real values back locally.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from mentormind.core.guard.pii.recognizers import PiiEntity

_TOKEN = re.compile(r"\[([A-Z][A-Z0-9_]*)_(\d+)\]")


class PiiVault(BaseModel):
    """Token <-> real value map of one masking session (one outbound call)."""

    max_entries: int = Field(default=5000, gt=0)
    token_by_key: dict[str, str] = Field(default_factory=dict)
    value_by_token: dict[str, str] = Field(default_factory=dict)
    counters: dict[str, int] = Field(default_factory=dict)

    def tokenize(self, value: str, entity: str) -> str:
        """Stable token for ``value``: the same value always maps to the same token."""
        key = f"{entity}\x00{_canonical(value, entity)}"
        token = self.token_by_key.get(key)
        if token is not None:
            return token
        if len(self.value_by_token) >= self.max_entries:
            raise OverflowError(f"PII vault full ({self.max_entries} entries)")
        self.counters[entity] = self.counters.get(entity, 0) + 1
        token = f"[{entity}_{self.counters[entity]}]"
        self.token_by_key[key] = token
        self.value_by_token[token] = value
        return token

    def restore(self, text: str) -> str:
        """Put real values back; tokens this vault did not issue are left untouched."""
        return _TOKEN.sub(lambda m: self.value_by_token.get(m.group(0), m.group(0)), text)

    def counts(self) -> dict[str, int]:
        """How many distinct values of each entity type were masked."""
        return dict(self.counters)

    def originals(self) -> list[str]:
        return list(self.value_by_token.values())


def _canonical(value: str, entity: str) -> str:
    if entity in (PiiEntity.PHONE, PiiEntity.ID, PiiEntity.CARD):
        digits = re.sub(r"\D", "", value)
        return "0" + digits[2:] if digits.startswith("84") and entity == PiiEntity.PHONE else digits
    return value.casefold()
