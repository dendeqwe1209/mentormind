"""Prompt templates of the VLM passes, stored as ``processing/vlm/prompts/*.md`` (spec 04 §4)."""

from __future__ import annotations

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


def render_prompt(name: str, **values: object) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").format(**values)
