"""The team's own inference server: Whisper, Docling and bge-m3 off this machine (spec 02, spec 03).

One base URL (``KNOWHOW_INFERENCE_URL``) serves three endpoints: ``/audio/transcriptions`` (ASR
provider ``remote``), ``/documents/convert`` (``KNOWHOW_DOC_EXTRACTOR=remote``) and ``/embeddings``
(``KNOWHOW_EMBEDDER=remote``). Local or cloud is judged from the URL exactly like the self-hosted
VLM's (:func:`is_private_url` + ``KNOWHOW_LOCAL_HOSTS``); each caller runs ``DataGuard`` with this
client as the destination BEFORE it sends anything (constitution art. 2).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from mentormind.core.config import Settings
from mentormind.core.providers.errors import ProviderConfigError
from mentormind.core.providers.openai_compat.locality import is_private_url
from mentormind.core.providers.transport import HttpxClient, RetryPolicy
from mentormind.core.providers.transport.http import redact_url

INFERENCE_URL_ENV = "KNOWHOW_INFERENCE_URL"
#: Connecting may take this long; the long ``KNOWHOW_INFERENCE_TIMEOUT_S`` is for the answer.
CONNECT_TIMEOUT_S = 10.0


class InferenceEndpoint(BaseModel):
    """Where the inference server is, how to authenticate, and whether calls leave the premises."""

    model_config = ConfigDict(frozen=True)

    base_url: str
    api_key: str | None = Field(default=None, repr=False)
    #: True unless the URL is private or declared in ``KNOWHOW_LOCAL_HOSTS``.
    is_cloud: bool
    timeout_s: float = 1800.0
    max_retries: int = 2

    @classmethod
    def resolve(
        cls,
        base_url: str | None,
        *,
        api_key: SecretStr | str | None = None,
        local_hosts: Iterable[str] = (),
        timeout_s: float = 1800.0,
        max_retries: int = 2,
    ) -> InferenceEndpoint:
        """Endpoint for ``base_url``; a blank key means no ``Authorization`` header.

        Raises:
            ProviderConfigError: no base URL (the message names ``KNOWHOW_INFERENCE_URL``).
        """
        if not base_url or not base_url.strip():
            raise ProviderConfigError(
                f"Chưa có địa chỉ máy chủ suy luận: đặt {INFERENCE_URL_ENV} (vd. https://gpu-box/v1)."
            )
        key = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        return cls(
            base_url=base_url.strip().rstrip("/"),
            api_key=(key or "").strip() or None,
            is_cloud=not is_private_url(base_url.strip(), local_hosts),
            timeout_s=timeout_s,
            max_retries=max_retries,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> InferenceEndpoint:
        """``KNOWHOW_INFERENCE_*``; an empty key falls back to ``KNOWHOW_VLM_API_KEY`` on the VLM's host."""
        return cls.resolve(
            settings.inference_url,
            api_key=inference_api_key(settings),
            local_hosts=settings.local_hosts,
            timeout_s=settings.inference_timeout_s,
            max_retries=settings.inference_max_retries,
        )


def inference_api_key(settings: Settings) -> SecretStr | None:
    """``KNOWHOW_INFERENCE_API_KEY``; blank values count as unset.

    Empty, it falls back to ``KNOWHOW_VLM_API_KEY`` only when ``KNOWHOW_VLM_BASE_URL`` has the same
    host as ``KNOWHOW_INFERENCE_URL`` (the self-hosted VLM box also serving inference): a cloud
    vendor's key forced there must never reach another server, over plain HTTP on a LAN least of all.
    """
    secrets = [settings.inference_api_key]
    if _same_host(settings.vlm_base_url, settings.inference_url):
        secrets.append(settings.vlm_api_key)
    for secret in secrets:
        if secret is not None and secret.get_secret_value().strip():
            return secret
    return None


def _same_host(a: str | None, b: str | None) -> bool:
    hosts = [urlsplit(url.strip()).hostname if url and url.strip() else None for url in (a, b)]
    return hosts[0] is not None and hosts[0] == hosts[1]


class InferenceClient:
    """Calls one inference server: bearer auth, long timeout, bounded retries (spec 04 FR-07 policy).

    Exposes ``name`` and ``is_cloud`` so it is a ``DataGuard`` destination itself.
    """

    name = "inference_server"

    def __init__(
        self,
        endpoint: InferenceEndpoint,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.endpoint = endpoint
        self._http = HttpxClient(
            timeout_s=endpoint.timeout_s,
            connect_timeout_s=min(CONNECT_TIMEOUT_S, endpoint.timeout_s),
            retry=RetryPolicy(max_retries=endpoint.max_retries),
            sleep=sleep,
            transport=transport,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> InferenceClient:
        """Raises: ProviderConfigError: ``KNOWHOW_INFERENCE_URL`` is not set."""
        return cls(InferenceEndpoint.from_settings(settings))

    @property
    def is_cloud(self) -> bool:
        return self.endpoint.is_cloud

    @property
    def shown_url(self) -> str:
        """The base URL without its ``user:password@`` (safe for logs and the CLI)."""
        return redact_url(self.endpoint.base_url)

    def post_json(self, path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._http.post_json(self._url(path), payload, headers=self._headers())

    def post_file(
        self, path: str, file: Path, *, data: Mapping[str, str | Sequence[str]] | None = None
    ) -> dict[str, Any]:
        return self._http.post_file(self._url(path), file, data=data, headers=self._headers())

    def _url(self, path: str) -> str:
        return f"{self.endpoint.base_url}/{path.lstrip('/')}"

    def _headers(self) -> dict[str, str]:
        key = self.endpoint.api_key
        return {"Authorization": f"Bearer {key}"} if key else {}
