from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/provider-diagnostics", tags=["health"])
def provider_diagnostics() -> dict[str, object]:
    """Safe provider diagnostics: booleans only, never secret values."""
    import os

    from mentormind.core.config import get_settings
    from mentormind.core.providers.vlm.factory import vlm_config_from_settings

    settings = get_settings()
    config = vlm_config_from_settings(settings)
    resolved_key = config.api_key.get_secret_value().strip() if config.api_key else ""
    return {
        "provider": settings.vlm_provider,
        "model": settings.vlm_model,
        "openrouter_env_present": bool((os.getenv("OPENROUTER_API_KEY") or "").strip()),
        "knowhow_vlm_env_present": bool((os.getenv("KNOWHOW_VLM_API_KEY") or "").strip()),
        "resolved_api_key_present": bool(resolved_key),
        "resolved_api_key_length": len(resolved_key),
    }
