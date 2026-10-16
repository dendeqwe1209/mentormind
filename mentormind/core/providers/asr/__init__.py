"""ASR (speech-to-text) providers (spec 03 FR-07c), built like the VLM and LLM kinds.

``base`` (interface: DataGuard before the audio is read), ``models``, ``registry``, ``factory``
(one provider per configuration and process), ``catalog`` (default models), ``backends/``
(``faster_whisper``, ``remote`` = the team's inference server, ``fake``). Importing this package
registers every backend; the engines' own libraries are imported only when a model is loaded.
"""

from mentormind.core.providers.asr.backends import fake, faster_whisper, remote
from mentormind.core.providers.asr.base import ASRProvider, Progress
from mentormind.core.providers.asr.factory import asr_config_from_settings, get_asr_provider
from mentormind.core.providers.asr.models import ASRResult, ASRSegment, ASRWord
from mentormind.core.providers.asr.registry import ASR_REGISTRY, register_asr

__all__ = [
    "ASR_REGISTRY",
    "ASRProvider",
    "ASRResult",
    "ASRSegment",
    "ASRWord",
    "Progress",
    "asr_config_from_settings",
    "fake",
    "faster_whisper",
    "get_asr_provider",
    "register_asr",
    "remote",
]
