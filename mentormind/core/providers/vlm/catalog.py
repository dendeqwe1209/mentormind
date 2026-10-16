"""Default Qwen3-VL-8B model id on each VLM provider (self-hosted: Ollama's Q4 ``qwen3-vl:8b``).

Vendors spell the same open-weight model differently; ``KNOWHOW_VLM_MODEL`` overrides this.
Check the vendor's model page before relying on an id — ids get renamed and retired.
"""

from __future__ import annotations

DEFAULT_VLM_MODELS: dict[str, str] = {
    # Ollama tag served by 3rdparty/vlm_server (Qwen3-VL-8B, Q4_K_M).
    "local_openai": "qwen3-vl:8b",
    # Alibaba retires this id on 2026-10-10 (notice of 2026-07-06).
    "qwen_api": "qwen3-vl-8b-instruct",
    "openrouter": "qwen/qwen3-vl-8b-instruct",
    "siliconflow": "Qwen/Qwen3-VL-8B-Instruct",
}


def default_vlm_model(provider: str) -> str | None:
    """Model id to use on ``provider`` when none is configured (None: must be configured)."""
    return DEFAULT_VLM_MODELS.get(provider)
