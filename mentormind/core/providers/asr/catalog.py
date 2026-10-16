"""Default model of each ASR provider (``KNOWHOW_ASR_MODEL`` overrides it).

``small`` (CTranslate2 conversion of Whisper small, ~480 MB, downloaded once from the Hugging Face
hub) is spec 03 FR-07's choice: good enough for Vietnamese on a CPU in int8. ``remote`` has none:
without ``KNOWHOW_ASR_MODEL`` the inference server runs its own default.
"""

from __future__ import annotations

DEFAULT_ASR_MODELS: dict[str, str] = {
    "faster_whisper": "small",
    "fake": "fake-asr",
}


def default_asr_model(provider: str) -> str | None:
    """Model to run on ``provider`` when none is configured (None: must be configured)."""
    return DEFAULT_ASR_MODELS.get(provider)
