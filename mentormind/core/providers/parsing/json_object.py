"""Tolerant extraction of the JSON object a model was asked to return.

A JSON mode on the endpoint is a strong hint, never a guarantee: models still wrap answers in
markdown fences or add a sentence. Callers therefore always parse through here and treat
:class:`InvalidJSONError` as "ask again with the repair prompt" (spec 04 §3).
"""

from __future__ import annotations

import json
import re
from typing import Any

from mentormind.core.providers.errors import InvalidJSONError

_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)


def parse_json_object(text: str) -> dict[str, Any]:
    """Return the JSON object in ``text`` or raise :class:`InvalidJSONError`."""
    candidate = text.strip()
    fenced = _FENCE.match(candidate)
    if fenced:
        candidate = fenced.group(1)
    for attempt in (candidate, _outermost_braces(candidate)):
        if not attempt:
            continue
        try:
            value = json.loads(attempt)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise InvalidJSONError("Model output is not a JSON object", raw_text=text)


def _outermost_braces(text: str) -> str:
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if 0 <= start < end else ""
