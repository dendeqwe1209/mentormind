"""Test doubles shared by the VLM tests."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field


class RecordingHttp(BaseModel):
    """HttpClient fake: records every POST, answers with a canned chat completion."""

    #: None = the server sent ``content: null`` (a thinking model that ran out of tokens while reasoning).
    content: str | None = '{"steps": []}'
    posts: list[tuple[str, dict[str, Any], dict[str, str]]] = Field(default_factory=list)

    def post_json(
        self, url: str, payload: Mapping[str, Any], *, headers: Mapping[str, str] | None = None
    ) -> dict[str, Any]:
        self.posts.append((url, dict(payload), dict(headers or {})))
        return {
            "choices": [{"message": {"role": "assistant", "content": self.content}}],
            "usage": {"prompt_tokens": 1200, "completion_tokens": 40, "total_tokens": 1240},
        }

    def get_json(self, url: str, *, headers: Mapping[str, str] | None = None) -> dict[str, Any]:
        raise AssertionError("unexpected GET")
