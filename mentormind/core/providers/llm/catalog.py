"""Default text model id on each LLM provider (``KNOWHOW_LLM_MODEL`` overrides it).

Checked 2026-09-28: DashScope ``qwen-plus`` is not on Alibaba's 2026-10-10 retirement list;
OpenRouter serves it as ``qwen/qwen-plus``. The self-hosted Qwen3-VL-8B server answers text too.
Providers without an entry (``siliconflow``, ``openai_compatible``) need ``KNOWHOW_LLM_MODEL``.
"""

from __future__ import annotations

DEFAULT_LLM_MODELS: dict[str, str] = {
    "local_openai": "qwen3-vl:8b",
    "qwen_api": "qwen-plus",
    "openrouter": "qwen/qwen-plus",
}


def default_llm_model(provider: str) -> str | None:
    return DEFAULT_LLM_MODELS.get(provider)
