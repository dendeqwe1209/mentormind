"""spec 04 FR-07 — provider transport: bounded retries with backoff, 90 s timeout."""

from __future__ import annotations

import httpx
import pytest

from mentormind.core.providers.errors import ProviderError
from mentormind.core.providers.transport import DEFAULT_TIMEOUT_S, HttpxClient, RetryPolicy

URL = "https://vendor.example/v1/chat/completions"


def client_for(responses: list[httpx.Response | Exception]) -> tuple[HttpxClient, list[float]]:
    queue = list(responses)
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    client = HttpxClient(
        retry=RetryPolicy(max_retries=3, base_delay_s=1.0, jitter=lambda: 0.0),
        sleep=sleeps.append,
        transport=httpx.MockTransport(handler),
    )
    return client, sleeps


def test_fr_07_default_timeout_is_90s() -> None:
    assert DEFAULT_TIMEOUT_S == 90.0


def test_fr_07_transient_errors_are_retried_with_exponential_backoff() -> None:
    client, sleeps = client_for(
        [
            httpx.Response(503),
            httpx.ConnectError("refused"),
            httpx.Response(429),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    assert client.post_json(URL, {"a": 1}) == {"ok": True}
    assert sleeps == [1.0, 2.0, 4.0]


def test_fr_07_gives_up_after_three_retries() -> None:
    client, sleeps = client_for([httpx.Response(502)] * 4)
    with pytest.raises(ProviderError) as info:
        client.post_json(URL, {})
    assert info.value.status_code == 502
    assert len(sleeps) == 3


def test_client_errors_are_not_retried() -> None:
    client, sleeps = client_for([httpx.Response(400, text="too many images")])
    with pytest.raises(ProviderError, match="too many images") as info:
        client.post_json(URL, {})
    assert info.value.status_code == 400
    assert sleeps == []


def test_retry_after_header_is_honoured() -> None:
    client, sleeps = client_for([httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, json={})])
    client.post_json(URL, {})
    assert sleeps == [7.0]


def test_basic_auth_in_the_base_url_is_sent_but_never_shown_in_errors() -> None:
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("Authorization"))
        return httpx.Response(401, text="401 Unauthorized")

    client = HttpxClient(retry=RetryPolicy(max_retries=0), transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as caught:
        client.post_json("https://admin:s3cret@tunnel.example/v1/chat/completions", {})
    assert seen == ["Basic YWRtaW46czNjcmV0"]  # base64("admin:s3cret")
    assert "s3cret" not in str(caught.value) and "https://tunnel.example/v1/chat/completions" in str(caught.value)
