"""A fake team inference server on ``httpx.MockTransport``: records requests, never opens a socket."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from email.parser import BytesParser
from email.policy import HTTP
from typing import Any, cast

import httpx

from mentormind.core.providers.inference import InferenceClient, InferenceEndpoint

#: A private address: the team's server reached over the LAN / Tailscale (counts as local).
PRIVATE_URL = "http://10.0.0.5:8000/v1"
#: A public host not declared in KNOWHOW_LOCAL_HOSTS (counts as cloud).
PUBLIC_URL = "https://user:s3cret@inference.example.com/v1"

Answer = httpx.Response | Mapping[str, Any] | Callable[[httpx.Request], httpx.Response]


class FakeInferenceServer:
    """Answers each path (``/v1/embeddings``...) with a canned JSON body, response or handler."""

    def __init__(self, answers: Mapping[str, Answer]) -> None:
        self.answers = dict(answers)
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        request.read()  # keep the body (a multipart upload is a stream)
        self.requests.append(request)
        path = request.url.path.removeprefix("/v1")
        answer = self.answers[path]
        if isinstance(answer, httpx.Response):
            return answer
        if callable(answer):
            return answer(request)
        return httpx.Response(200, json=dict(answer))

    def client(
        self, url: str = PRIVATE_URL, *, api_key: str | None = None, local_hosts: Iterable[str] = ()
    ) -> InferenceClient:
        endpoint = InferenceEndpoint.resolve(url, api_key=api_key, local_hosts=local_hosts, max_retries=0)
        return InferenceClient(endpoint, transport=httpx.MockTransport(self.handle))


def multipart(request: httpx.Request) -> tuple[dict[str, list[str]], dict[str, tuple[str, bytes]]]:
    """Form fields (name -> values) and files (name -> (filename, bytes)) of a multipart request."""
    head = f"Content-Type: {request.headers['content-type']}\r\n\r\n".encode()
    message = BytesParser(policy=HTTP).parsebytes(head + request.content)
    fields: dict[str, list[str]] = {}
    files: dict[str, tuple[str, bytes]] = {}
    for part in message.iter_parts():
        name = str(part.get_param("name", header="content-disposition"))
        payload = cast(bytes, part.get_payload(decode=True))
        filename = part.get_filename()
        if filename is None:
            fields.setdefault(name, []).append(payload.decode())
        else:
            files[name] = (filename, payload)
    return fields, files
