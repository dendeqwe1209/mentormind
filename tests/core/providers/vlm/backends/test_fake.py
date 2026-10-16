"""FakeVLM — scripted answers and call recording."""

from __future__ import annotations

from pathlib import Path

import pytest

from mentormind.core.config import REPO_ROOT, Settings
from mentormind.core.providers.errors import InvalidJSONError
from mentormind.core.providers.models import ProviderConfig
from mentormind.core.providers.vlm import VLM_REGISTRY
from mentormind.core.providers.vlm.backends.fake import FakeVLM

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "vlm"


def test_fake_vlm_replays_fixture_and_records_calls(settings: Settings, frames: list[Path]) -> None:
    config = ProviderConfig(provider="fake", options={"fixture": str(FIXTURES / "pass_a_two_steps.json")})
    fake = VLM_REGISTRY.create(config)
    assert isinstance(fake, FakeVLM) and not fake.is_cloud
    data = fake.generate_json(frames, "p", {}, classification="factory_confidential")
    steps = [s["step"] for s in data["steps"]]
    assert steps == ["Nhặt linh kiện A", "Đặt linh kiện A vào ngăn trái"]
    assert fake.calls[0].frames == tuple(frames)


def test_fake_vlm_script_repeats_last_answer(frames: list[Path]) -> None:
    fake = FakeVLM(["not json", {"steps": []}])
    with pytest.raises(InvalidJSONError):
        fake.generate_json(frames, "p", {}, classification="synthetic")
    for _ in range(2):
        assert fake.generate_json(frames, "p", {}, classification="synthetic") == {"steps": []}
