"""Look up a named secret: process environment first, then the repo's ``.env``.

Provider API keys have vendor-specific names (``OPENROUTER_API_KEY``, ``DASHSCOPE_API_KEY``...)
so several keys can sit side by side and switching provider is only ``KNOWHOW_VLM_PROVIDER``.
``.env`` is gitignored; ``.secrets/README.md`` explains how to obtain each vendor's key.
Constitution art. 6: no secret is ever hardcoded.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from dotenv import dotenv_values


def lookup_secret(name: str, *, secrets_file: Path, environ: Mapping[str, str] | None = None) -> str | None:
    """Return the non-empty value of secret ``name``, or None when it is not configured."""
    env = os.environ if environ is None else environ
    value = (env.get(name) or "").strip()
    if value:
        return value
    if secrets_file.is_file():
        value = (dotenv_values(secrets_file).get(name) or "").strip()
        if value:
            return value
    return None
