# MentorMind live image for Railway: React frontend + FastAPI backend in one service.
FROM node:22-bookworm-slim AS frontend
WORKDIR /build/mentormind/frontend
COPY mentormind/frontend/package.json mentormind/frontend/package-lock.json ./
RUN npm ci
COPY mentormind/frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm AS app
ENV PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_CACHE_DIR=/tmp/uv-cache \
    PATH="/opt/venv/bin:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ffmpeg curl ca-certificates libglib2.0-0 postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /uvx /usr/local/bin/
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project \
    --extra api --extra kg --extra video --extra vlm

COPY mentormind ./mentormind
COPY docs/contracts ./docs/contracts
COPY infra ./infra
COPY data/mock_sigma ./data/mock_sigma
COPY data/demo ./data/demo
COPY scripts ./scripts
COPY --from=frontend /build/mentormind/frontend/dist ./mentormind/frontend/dist

RUN uv sync --frozen --extra api --extra kg --extra video --extra vlm \
    && uv pip install --python /opt/venv/bin/python \
       --index-url https://download.pytorch.org/whl/cpu torch \
    && chmod +x scripts/railway-start.sh \
    && rm -rf /tmp/uv-cache

EXPOSE 8000
CMD ["bash", "scripts/railway-start.sh"]
