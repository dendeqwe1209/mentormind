"""Wire format of the OpenAI-compatible VLM backend."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from mentormind.core.config import Settings
from mentormind.core.providers.errors import InvalidJSONError
from mentormind.core.providers.models import TokenUsage
from mentormind.core.providers.vlm import get_vlm_provider
from tests.core.providers.fakes import RecordingHttp


def with_provider(settings: Settings, **update: Any) -> Settings:
    return settings.model_copy(update=update)


def test_frames_are_sent_in_order_as_base64_images_after_the_prompt(
    settings: Settings, http: RecordingHttp, frames: list[Path]
) -> None:
    vlm = get_vlm_provider(settings, http=http)
    response = vlm.generate(frames, "Các ảnh sau...", classification="synthetic", temperature=0.2)

    url, payload, _ = http.posts[0]
    assert url == "http://127.0.0.1:11434/v1/chat/completions"
    assert payload["model"] == "qwen3-vl:8b"
    assert payload["temperature"] == 0.2
    parts = payload["messages"][-1]["content"]
    assert parts[0] == {"type": "text", "text": "Các ảnh sau..."}
    for part, path in zip(parts[1:], frames, strict=True):
        prefix, encoded = part["image_url"]["url"].split(",", 1)
        assert prefix == "data:image/jpeg;base64"
        assert base64.b64decode(encoded) == path.read_bytes()
    assert response.usage == TokenUsage(prompt_tokens=1200, completion_tokens=40)
    assert (response.provider, response.model) == ("local_openai", "qwen3-vl:8b")


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        ("local_openai", "json_schema"),
        ("openrouter", "json_schema"),
        ("qwen_api", "json_object"),
        ("siliconflow", "json_object"),
    ],
)
def test_json_mode_auto_uses_what_each_endpoint_honours(
    settings: Settings, http: RecordingHttp, provider: str, expected: str
) -> None:
    settings = with_provider(settings, vlm_provider=provider, vlm_api_key=SecretStr("k"))
    get_vlm_provider(settings, http=http).generate_json([], "trả JSON", {"type": "object"}, classification="public")
    assert http.posts[0][1]["response_format"]["type"] == expected


def test_json_mode_off_sends_no_response_format(settings: Settings, http: RecordingHttp) -> None:
    vlm = get_vlm_provider(with_provider(settings, vlm_json_mode="off"), http=http)
    vlm.generate_json([], "trả JSON", {"type": "object"}, classification="public")
    assert "response_format" not in http.posts[0][1]


def test_generate_json_parses_fenced_answer(settings: Settings, frames: list[Path]) -> None:
    http = RecordingHttp(content='```json\n{"steps": [{"step": "Đặt hộp"}]}\n```')
    vlm = get_vlm_provider(settings, http=http)
    data = vlm.generate_json(frames, "p", {"type": "object"}, classification="synthetic")
    assert data == {"steps": [{"step": "Đặt hộp"}]}


def test_generate_json_raises_invalid_json_with_raw_text(settings: Settings) -> None:
    vlm = get_vlm_provider(settings, http=RecordingHttp(content="xin lỗi, tôi không thấy gì"))
    with pytest.raises(InvalidJSONError) as info:
        vlm.generate_json([], "p", {"type": "object"}, classification="synthetic")
    assert "xin lỗi" in info.value.raw_text


def test_ac_29_a_null_answer_is_an_empty_answer_not_a_provider_error(settings: Settings, frames: list[Path]) -> None:
    vlm = get_vlm_provider(settings, http=RecordingHttp(content=None))
    assert vlm.generate(frames, "p", classification="synthetic").text == ""
    with pytest.raises(InvalidJSONError):  # what pass A and pass C already handle per segment
        vlm.generate_json(frames, "p", {"type": "object"}, classification="synthetic")
