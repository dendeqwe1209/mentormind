.PHONY: start demo-ui up down dev-up dev-shell check test demo fmt vlm-server vlm-server-stop vlm-server-smoke

# Khởi động toàn bộ Backend + Tablet Frontend chỉ bằng 1 lệnh
start:
	./start.sh

demo-ui:
	./start.sh

# spec 01 FR-05 / task D3. docker-compose.yml stays at the repo root; every override lives in
# infra/docker/ and is selected by PLATFORM (or by spelling COMPOSE_FILES out yourself):
#   make up PLATFORM=rocm      AMD GPU box (MI250: one GCD)
#   make up PLATFORM=devbox    rootless Docker: GPU through CDI + host network
OVERRIDES_rocm   = -f infra/docker/docker-compose.rocm.yml
OVERRIDES_devbox = -f infra/docker/docker-compose.cdi.yml -f infra/docker/docker-compose.devbox.yml
OVERRIDES_cdi    = -f infra/docker/docker-compose.cdi.yml
COMPOSE_FILES ?= -f docker-compose.yml $(OVERRIDES_$(PLATFORM))
COMPOSE = docker compose $(COMPOSE_FILES)

# Whole dev stack: mentormind + vlm-server + PostgreSQL/pgvector + Neo4j (profile lite).
up:
	$(COMPOSE) --profile lite up -d --build

down:
	$(COMPOSE) --profile lite down

# Only the two dev containers (vlm-server = Ollama; it pulls qwen3-vl:8b on first start).
dev-up:
	$(COMPOSE) up -d --build mentormind vlm-server

dev-shell:
	$(COMPOSE) exec mentormind bash

# spec 01 FR-04; constitution art. 6 (mypy --strict for core/schemas and core/guard).
check:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	uv run mypy --strict mentormind/core/schemas mentormind/core/guard
	uv run pytest

test:
	uv run pytest

demo:
	bash scripts/demo.sh

fmt:
	uv run ruff format .
	uv run ruff check --fix .

# spec 04 FR-08: self-hosted Qwen3-VL-8B (Q4) on Ollama without Docker, macOS or Linux
# (mentormind-inference, 3rdparty/vlm_server). Settings: VLM_SERVER_* in .env, or flags (--help).
vlm-server:
	env $$(grep -sE '^(VLM_SERVER_[A-Z_]+|VLM_GPU)=[^[:space:]]' .env | sed 's/[[:space:]]*#.*//') \
		bash 3rdparty/vlm_server/scripts/serve-ollama.sh

vlm-server-stop:
	bash 3rdparty/vlm_server/scripts/serve-ollama.sh --stop

vlm-server-smoke:
	uv run knowhow vlm ping --frames 8
