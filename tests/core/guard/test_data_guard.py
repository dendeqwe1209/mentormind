"""spec 01 AC-05 — DataGuard blocks factory_confidential data from cloud providers."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from mentormind.core.guard import ConfidentialDataError, DataGuard


class Destination(BaseModel):
    name: str
    is_cloud: bool


CLOUD = Destination(name="openrouter", is_cloud=True)
LOCAL = Destination(name="local_openai", is_cloud=False)


def test_ac_05_confidential_to_cloud_raises() -> None:
    with pytest.raises(ConfidentialDataError, match="openrouter"):
        DataGuard.check("factory_confidential", CLOUD)


def test_ac_05_confidential_to_local_allowed() -> None:
    DataGuard.check("factory_confidential", LOCAL)


@pytest.mark.parametrize("label", ["public", "synthetic"])
def test_non_confidential_data_may_go_to_cloud(label: str) -> None:
    DataGuard.check(label, CLOUD)


def test_unknown_label_fails_closed() -> None:
    with pytest.raises(ValueError):
        DataGuard.check("top_secret", LOCAL)
