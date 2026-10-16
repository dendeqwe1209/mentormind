"""Turn a :class:`ProviderConfig` into a concrete OpenAI-compatible endpoint, for any kind.

Resolution order: explicit config first, then the vendor row of ``OPENAI_COMPAT_ENDPOINTS``, then
the kind's default model id. A vendor row that is cloud stays cloud; anything else (the
self-hosted server, ``openai_compatible``) is judged by where its URL points, so a "local"
provider aimed at a public host is still guarded like the cloud.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from mentormind.core.config import JsonMode
from mentormind.core.providers.errors import ProviderConfigError
from mentormind.core.providers.models import ProviderConfig
from mentormind.core.providers.openai_compat.endpoints import OPENAI_COMPAT_ENDPOINTS
from mentormind.core.providers.openai_compat.locality import is_private_url

SECRETS_GUIDE = ".secrets/README.md"


class ResolvedEndpoint(BaseModel):
    """Everything a chat client needs to call one endpoint."""

    model_config = ConfigDict(frozen=True)

    name: str
    base_url: str
    model: str
    is_cloud: bool
    api_key: str | None = Field(default=None, repr=False)
    json_mode: JsonMode


def api_key_env_for(name: str) -> str | None:
    """Secret variable of the vendor registered as ``name`` (None: keyless or generic)."""
    endpoint = OPENAI_COMPAT_ENDPOINTS.get(name)
    return endpoint.api_key_env if endpoint else None


def base_url_env_for(name: str) -> str | None:
    """Secret variable that may override the vendor's base URL (None: fixed URL)."""
    endpoint = OPENAI_COMPAT_ENDPOINTS.get(name)
    return endpoint.base_url_env if endpoint else None


def resolve_endpoint(config: ProviderConfig, *, default_model: str | None, env_prefix: str) -> ResolvedEndpoint:
    """Resolve ``config`` or raise :class:`ProviderConfigError` saying which variable to set.

    Args:
        config: The provider config (``provider`` is the registry name).
        default_model: The kind's model id for this vendor when none is configured.
        env_prefix: ``"VLM"`` or ``"LLM"``, used to name the variable in error messages.
    """
    name = config.provider
    endpoint = OPENAI_COMPAT_ENDPOINTS.get(name)
    base_url = config.base_url or (endpoint.base_url if endpoint else None)
    if not base_url:
        raise ProviderConfigError(
            f"Provider '{name}' cần địa chỉ server: đặt KNOWHOW_{env_prefix}_BASE_URL (vd. http://gpu-box:11434/v1)."
        )
    model = config.model or default_model
    if not model:
        raise ProviderConfigError(f"Provider '{name}' cần tên model: đặt KNOWHOW_{env_prefix}_MODEL.")
    api_key = config.api_key.get_secret_value() if config.api_key else None
    if endpoint and endpoint.is_cloud and not api_key:
        raise ProviderConfigError(
            f"Thiếu API key cho provider '{name}': thêm {endpoint.api_key_env}=... vào "
            f".env (cách lấy key: {SECRETS_GUIDE})."
        )
    json_mode = config.json_mode
    if json_mode == "auto":
        json_mode = endpoint.json_mode if endpoint else "off"
    return ResolvedEndpoint(
        name=name,
        base_url=base_url.rstrip("/"),
        model=model,
        is_cloud=bool(endpoint and endpoint.is_cloud) or not is_private_url(base_url, config.local_hosts),
        api_key=api_key,
        json_mode=json_mode,
    )
