"""spec 04 AC-03, AC-13 — confidential data never reaches a cloud provider, not even its files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from mentormind.core.config import Settings
from mentormind.core.guard import ConfidentialDataError
from mentormind.core.providers import vlm as vlm_providers
from mentormind.core.providers.llm import get_llm_provider
from mentormind.core.providers.vlm import get_vlm_provider
from mentormind.core.providers.vlm.backends.fake import FakeVLM
from mentormind.core.providers.vlm.models import ImageInput
from tests.core.providers.fakes import RecordingHttp


def with_provider(settings: Settings, **update: Any) -> Settings:
    return settings.model_copy(update=update)


def test_ac_03_confidential_video_cloud_provider_raises_before_reading_files(
    frames: list[Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[Path] = []
    real_read = vlm_providers.base.read_image

    def spy(path: Path) -> ImageInput:
        opened.append(path)
        return real_read(path)

    monkeypatch.setattr(vlm_providers.base, "read_image", spy)
    cloud = FakeVLM(is_cloud=True, name="openrouter")
    with pytest.raises(ConfidentialDataError):
        cloud.generate(frames, "mô tả", classification="factory_confidential")
    assert opened == []
    assert cloud.calls == []


def test_ac_03_cloud_http_provider_sends_nothing(settings: Settings, http: RecordingHttp, frames: list[Path]) -> None:
    settings = with_provider(settings, vlm_provider="openrouter", vlm_api_key=SecretStr("sk"))
    vlm = get_vlm_provider(settings, http=http)
    assert vlm.is_cloud
    with pytest.raises(ConfidentialDataError):
        vlm.generate(frames, "mô tả", classification="factory_confidential")
    assert http.posts == []


def test_ac_03_self_hosted_provider_accepts_confidential(
    settings: Settings, http: RecordingHttp, frames: list[Path]
) -> None:
    vlm = get_vlm_provider(settings, http=http)
    assert vlm.name == "local_openai" and not vlm.is_cloud
    vlm.generate(frames, "mô tả", classification="factory_confidential")
    assert len(http.posts) == 1


def test_ac_13_local_provider_aimed_at_public_host_counts_as_cloud(
    settings: Settings, http: RecordingHttp, frames: list[Path]
) -> None:
    settings = with_provider(settings, vlm_base_url="https://vlm.example.com/v1")
    vlm = get_vlm_provider(settings, http=http)
    assert vlm.is_cloud
    with pytest.raises(ConfidentialDataError):
        vlm.generate(frames, "mô tả", classification="factory_confidential")


NGROK = "https://user:pass@VLM-team.ngrok-free.dev/v1"


def test_ac_23_declared_local_host_is_local_and_accepts_confidential(
    settings: Settings, http: RecordingHttp, frames: list[Path]
) -> None:
    settings = with_provider(settings, vlm_base_url=NGROK, local_hosts=["vlm-team.ngrok-free.dev"])
    vlm = get_vlm_provider(settings, http=http)
    assert not vlm.is_cloud
    vlm.generate(frames, "mô tả", classification="factory_confidential")
    assert len(http.posts) == 1


def test_ac_23_llm_following_the_vlm_is_local_too(settings: Settings, http: RecordingHttp) -> None:
    settings = with_provider(settings, vlm_base_url=NGROK, local_hosts=["vlm-team.ngrok-free.dev"])
    assert not get_llm_provider(settings, http=http).is_cloud


@pytest.mark.parametrize(
    ("update", "why"),
    [
        ({"vlm_base_url": NGROK}, "empty list: AC-13 unchanged"),
        ({"vlm_base_url": "https://x.vlm-team.ngrok-free.dev/v1"}, "subdomain is another host"),
        ({"vlm_base_url": "https://other.ngrok-free.dev/v1"}, "another public host"),
        (
            {"vlm_provider": "openrouter", "vlm_api_key": SecretStr("sk"), "local_hosts_extra": ["openrouter.ai"]},
            "a cloud vendor stays cloud",
        ),
    ],
)
def test_ac_23_anything_not_declared_stays_cloud(
    settings: Settings, http: RecordingHttp, frames: list[Path], update: dict[str, Any], why: str
) -> None:
    hosts = ["vlm-team.ngrok-free.dev", *update.pop("local_hosts_extra", [])]
    if why.startswith("empty"):
        hosts = []
    vlm = get_vlm_provider(with_provider(settings, local_hosts=hosts, **update), http=http)
    assert vlm.is_cloud, why
    with pytest.raises(ConfidentialDataError):
        vlm.generate(frames, "mô tả", classification="factory_confidential")
    assert http.posts == []
