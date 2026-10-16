"""Agent prompts live in each agent's ``prompts/*.md``, never in Python (spec 06 FR-05)."""

from __future__ import annotations

from pathlib import Path


class PromptBook:
    """The ``prompts/`` folder of one agent; ``render`` fills a template with ``str.format``."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def render(self, name: str, **values: object) -> str:
        return (self.directory / name).read_text(encoding="utf-8").format(**values)
