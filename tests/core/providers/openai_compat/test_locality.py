"""Local-vs-cloud decision for endpoint URLs."""

from __future__ import annotations

import pytest

from mentormind.core.providers.openai_compat import is_private_url


@pytest.mark.parametrize(
    ("url", "private"),
    [
        ("http://127.0.0.1:8100/v1", True),
        ("http://localhost:8100/v1", True),
        ("http://192.168.1.20:8100/v1", True),
        ("http://10.0.0.5/v1", True),
        ("http://100.101.102.103:8100/v1", True),  # Tailscale / CGNAT
        ("http://gpu-box:8100/v1", True),
        ("http://gpu-box.local:8100/v1", True),
        ("https://openrouter.ai/api/v1", False),
        ("http://8.8.8.8/v1", False),
        ("not a url", False),
    ],
)
def test_is_private_url(url: str, private: bool) -> None:
    assert is_private_url(url) is private


def test_ac_23_declared_hosts_match_the_whole_name_case_insensitively() -> None:
    hosts = ["vlm-team.ngrok-free.dev"]
    assert is_private_url("https://u:p@VLM-Team.ngrok-free.dev/v1", local_hosts=hosts)
    assert not is_private_url("https://x.vlm-team.ngrok-free.dev/v1", local_hosts=hosts)
    assert not is_private_url("https://vlm-team.ngrok-free.dev.evil.com/v1", local_hosts=hosts)
    assert not is_private_url("https://vlm-team.ngrok-free.dev/v1")
