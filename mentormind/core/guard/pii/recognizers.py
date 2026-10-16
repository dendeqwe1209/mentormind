"""Free-text PII recognizers — the Vietnamese patterns of bankassist-mcp (SPEC §4.1).

Order matters, longest first: card (Luhn) → email → VN mobile → CCCD (12 digits) → CMND (9
digits, only with an ID keyword nearby so amounts such as ``500000000`` survive).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

_ID_KEYWORDS = ("cmnd", "cmt", "chung minh nhan dan", "chung minh thu", "giay to tuy than")
_CONTEXT_WINDOW = 40


class PiiEntity(StrEnum):
    PERSON = "PERSON"
    PHONE = "PHONE"
    EMAIL = "EMAIL"
    ID = "ID"
    CARD = "CARD"


def strip_diacritics(text: str) -> str:
    """Lower-case ASCII folding of Vietnamese text ("Chứng minh" -> "chung minh")."""
    decomposed = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def luhn_valid(digits: str) -> bool:
    total = 0
    for i, char in enumerate(reversed(digits)):
        value = int(char)
        if i % 2 == 1:
            value = value * 2 - 9 if value > 4 else value * 2
        total += value
    return total % 10 == 0


class Recognizer(BaseModel):
    """One free-text pattern for one entity type."""

    model_config = ConfigDict(frozen=True)

    entity: str
    pattern: re.Pattern[str]
    #: When set, a match counts only if one of these (diacritics-free) words is nearby.
    context_keywords: tuple[str, ...] = ()
    #: Card numbers: the digits must pass the Luhn check.
    luhn: bool = False

    def find(self, text: str) -> list[tuple[int, int]]:
        spans = []
        for match in self.pattern.finditer(text):
            start, end = match.span()
            if self.luhn and not luhn_valid(re.sub(r"\D", "", match.group())):
                continue
            if self.context_keywords and not self._keyword_near(text, start, end):
                continue
            spans.append((start, end))
        return spans

    def _keyword_near(self, text: str, start: int, end: int) -> bool:
        window = strip_diacritics(text[max(0, start - _CONTEXT_WINDOW) : min(len(text), end + _CONTEXT_WINDOW)])
        return any(keyword in window for keyword in self.context_keywords)


DEFAULT_RECOGNIZERS: tuple[Recognizer, ...] = (
    Recognizer(
        entity=PiiEntity.CARD,
        pattern=re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)"),
        luhn=True,
    ),
    Recognizer(
        entity=PiiEntity.EMAIL,
        pattern=re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    ),
    Recognizer(
        entity=PiiEntity.PHONE,
        pattern=re.compile(r"(?<!\d)(?:\+84|0)[\s.\-]?[35789](?:[\s.\-]?\d){8}(?!\d)"),
    ),
    Recognizer(entity=PiiEntity.ID, pattern=re.compile(r"(?<!\d)\d{12}(?!\d)")),
    Recognizer(
        entity=PiiEntity.ID,
        pattern=re.compile(r"(?<!\d)\d{9}(?!\d)"),
        context_keywords=_ID_KEYWORDS,
    ),
)


def custom_recognizers(patterns: Mapping[str, str]) -> tuple[Recognizer, ...]:
    """Recognizers for site-specific codes, e.g. ``{"EQUIPMENT": "SIGMA-EQ-\\d+"}``."""
    return tuple(Recognizer(entity=entity.upper(), pattern=re.compile(regex)) for entity, regex in patterns.items())
