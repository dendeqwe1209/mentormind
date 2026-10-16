"""``get_asr_provider`` — the only way business code obtains speech-to-text (spec 03 FR-07c).

One provider per configuration and process: the engine loads its model on first use and every
later job of the process reuses it (a Whisper model costs seconds to load and hundreds of MB).
"""

from __future__ import annotations

import threading

from mentormind.core.config import Settings, get_settings
from mentormind.core.providers.asr.base import ASRProvider
from mentormind.core.providers.asr.catalog import default_asr_model
from mentormind.core.providers.asr.registry import ASR_REGISTRY
from mentormind.core.providers.inference import inference_api_key
from mentormind.core.providers.models import ProviderConfig

_BUILT: dict[str, ASRProvider] = {}
_LOCK = threading.Lock()


def asr_config_from_settings(settings: Settings) -> ProviderConfig:
    """Translate ``KNOWHOW_ASR_*`` settings (+ ``KNOWHOW_INFERENCE_*`` for ``remote``) into a config."""
    return ProviderConfig(
        provider=settings.asr_provider,
        model=settings.asr_model or default_asr_model(settings.asr_provider),
        # The team's inference server; only the ``remote`` backend reads these.
        base_url=settings.inference_url or None,
        api_key=inference_api_key(settings),
        timeout_s=settings.inference_timeout_s,
        max_retries=settings.inference_max_retries,
        local_hosts=tuple(settings.local_hosts),
        options={
            "device": settings.asr_device,
            "compute_type": settings.asr_compute_type,
            "beam_size": settings.asr_beam_size,
            "language": settings.asr_language or None,
            "vad_filter": settings.asr_vad,
        },
    )


def get_asr_provider(settings: Settings | None = None) -> ASRProvider:
    """The ASR provider selected by ``KNOWHOW_ASR_PROVIDER``, built once per configuration.

    Raises:
        ProviderConfigError: unknown provider name (the message lists the registered ones), or
            ``remote`` without ``KNOWHOW_INFERENCE_URL``.
    """
    config = asr_config_from_settings(settings or get_settings())
    key = config.model_dump_json()
    with _LOCK:
        provider = _BUILT.get(key)
        if provider is None:
            provider = ASR_REGISTRY.create(config)
            _BUILT[key] = provider
    return provider
