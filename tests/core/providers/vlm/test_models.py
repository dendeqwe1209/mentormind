"""Provider data models validate their fields (pydantic)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mentormind.core.guard.image import ImageGuardPolicy
from mentormind.core.providers.models import TokenUsage
from mentormind.core.providers.vlm.models import ImageInput


def test_models_validate_their_fields() -> None:
    with pytest.raises(ValidationError):
        TokenUsage(prompt_tokens=-1, completion_tokens=0)
    with pytest.raises(ValidationError):
        ImageInput.model_validate({"path": "a.gif", "mime_type": "image/gif", "data": b""})
    with pytest.raises(ValidationError):
        ImageGuardPolicy(score_threshold=1.5)
