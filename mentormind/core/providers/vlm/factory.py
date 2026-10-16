"""``get_vlm_provider`` — the only way business code obtains a VLM (spec 04 FR-01).

Code never imports a concrete provider class; switching self-host <-> cloud is config only
(constitution art. 5).
"""

from __future__ import annotations

from pydantic import SecretStr

from mentormind.core.config import Settings, get_settings, lookup_secret
from mentormind.core.guard import GuardPolicy
from mentormind.core.guard.image import ImageGuardPolicy
from mentormind.core.providers.models import ProviderConfig
from mentormind.core.providers.transport import HttpClient
from mentormind.core.providers.vlm.base import VLMProvider
from mentormind.core.providers.vlm.registry import VLM_REGISTRY


def vlm_config_from_settings(settings: Settings) -> ProviderConfig:
    """Translate ``KNOWHOW_VLM_*`` settings (+ the provider's own secret) into a config."""
    # ``KNOWHOW_VLM_API_KEY=`` (blank line in .env) arrives as SecretStr(""): treat as unset.
    api_key = settings.vlm_api_key if _non_blank(settings.vlm_api_key) else None
    provider_cls = VLM_REGISTRY.get(settings.vlm_provider)
    key_env = provider_cls.api_key_env(settings.vlm_provider) if provider_cls else None
    if api_key is None and key_env:
        found = lookup_secret(key_env, secrets_file=settings.secrets_file)
        api_key = SecretStr(found) if found else None
    base_url = settings.vlm_base_url or None
    url_env = provider_cls.base_url_env(settings.vlm_provider) if provider_cls else None
    if base_url is None and url_env:
        base_url = lookup_secret(url_env, secrets_file=settings.secrets_file)
    return ProviderConfig(
        provider=settings.vlm_provider,
        model=settings.vlm_model or None,
        base_url=base_url,
        api_key=api_key,
        timeout_s=settings.vlm_timeout_s,
        max_retries=settings.vlm_max_retries,
        json_mode=settings.vlm_json_mode,
        max_tokens=settings.vlm_max_tokens,
        extra_body=settings.vlm_extra_body,
        local_hosts=tuple(settings.local_hosts),
    )


def _non_blank(secret: SecretStr | None) -> bool:
    return secret is not None and bool(secret.get_secret_value().strip())


def get_vlm_provider(settings: Settings | None = None, *, http: HttpClient | None = None) -> VLMProvider:
    """Build the VLM provider selected by ``KNOWHOW_VLM_PROVIDER``.

    Raises:
        ProviderConfigError: unknown provider name, missing key or base URL.
    """
    settings = settings or get_settings()
    provider = VLM_REGISTRY.create(vlm_config_from_settings(settings), http)
    provider.guard_policy = GuardPolicy(
        mask_text=settings.guard_mask_text,
        audit_dir=settings.guard_audit_dir,
        extra_patterns=settings.guard_extra_patterns,
    )
    provider.image_policy = ImageGuardPolicy(blur_faces=settings.guard_blur_faces, face_model=settings.guard_face_model)
    return provider
