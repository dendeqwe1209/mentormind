# syntax=docker/dockerfile:1
# Mentor Mind dev container: Python 3.11, uv, ffmpeg and every extra of pyproject.toml.
# docker-compose.yml bind-mounts the repo at /workspace; the venv lives outside it (/opt/venv),
# so the host's .venv is never touched and code edits on the host are live in the container.
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_CACHE_DIR=/tmp/uv-cache \
    PATH="/opt/venv/bin:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg git make curl ca-certificates libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && git config --system --add safe.directory /workspace
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /uvx /usr/local/bin/

WORKDIR /workspace
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --all-extras --no-install-project
COPY mentormind ./mentormind
# Rootful Docker runs the container as DEV_UID (docker-compose.yml): `uv run` re-syncs the editable
# project into /opt/venv and needs a cache, so the venv is writable by any UID and the root-owned
# build cache is dropped (uv recreates it under the world-writable /tmp).
RUN uv sync --frozen --all-extras \
    && chmod -R a+rwX /opt/venv \
    && rm -rf /tmp/uv-cache

# Work inside with:  docker compose exec mentormind bash
CMD ["sleep", "infinity"]
