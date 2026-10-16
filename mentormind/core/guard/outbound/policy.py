"""GuardPolicy — what the outbound guard does for cloud calls (``KNOWHOW_GUARD_*``)."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class GuardPolicy(BaseModel):
    """What the outbound guard does for cloud calls (``KNOWHOW_GUARD_*`` settings)."""

    model_config = ConfigDict(frozen=True)

    mask_text: bool = True
    audit_dir: Path | None = None
    #: Site-specific codes to mask, entity -> regex (e.g. {"EQUIPMENT": "SIGMA-EQ-\\d+"}).
    extra_patterns: dict[str, str] = Field(default_factory=dict)
    #: Values known to be sensitive, entity -> values (e.g. {"PERSON": ["Nguyễn Văn A"]}).
    known_entities: dict[str, list[str]] = Field(default_factory=dict)
