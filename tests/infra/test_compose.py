"""spec 01 FR-05, AC-07 (task D3) — the compose file keeps the demo stack small and local."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from mentormind.core.config import REPO_ROOT
from mentormind.core.providers.openai_compat import is_private_url

LITE_STACK = ("mentormind", "postgres", "neo4j")
UNITS = {"k": 1 / 1024 / 1024, "m": 1 / 1024, "g": 1.0}
OVERRIDES_DIR = REPO_ROOT / "infra" / "docker"


class ComposeLoader(yaml.SafeLoader):
    """SafeLoader that tolerates Compose's own tags (``deploy: !reset {}`` in the overrides)."""


ComposeLoader.add_multi_constructor("!", lambda loader, suffix, node: None)


def load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = yaml.load(path.read_text(), Loader=ComposeLoader)
    return data


def compose() -> dict[str, Any]:
    return load(REPO_ROOT / "docker-compose.yml")


def services() -> dict[str, Any]:
    result: dict[str, Any] = compose()["services"]
    return result


def default(value: str) -> str:
    """``${VAR:-fallback}`` -> ``fallback``; plain values unchanged."""
    match = re.fullmatch(r"\$\{\w+:-([^}]*)\}", value)
    return match.group(1) if match else value


def gib(limit: str) -> float:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([kmg])", default(str(limit)).lower())
    assert match, limit
    return float(match.group(1)) * UNITS[match.group(2)]


def test_ac_07_every_service_has_a_memory_limit() -> None:
    for name, service in services().items():
        assert "mem_limit" in service, name


def test_ac_07_lite_demo_stack_fits_in_4_gib() -> None:
    assert sum(gib(services()[name]["mem_limit"]) for name in LITE_STACK) <= 4.0


def test_fr_05_neo4j_has_apoc_and_small_heap_and_page_cache() -> None:
    neo4j = services()["neo4j"]
    env = neo4j["environment"]
    assert neo4j["image"].startswith("neo4j:5")
    assert "apoc" in env["NEO4J_PLUGINS"]
    assert env["NEO4J_server_memory_heap_max__size"] == "1G"
    assert env["NEO4J_server_memory_pagecache_size"] == "512M"
    assert "healthcheck" in neo4j


def test_fr_05_postgres_runs_pgvector_with_the_init_script() -> None:
    postgres = services()["postgres"]
    assert postgres["image"] == "pgvector/pgvector:pg16"
    assert any("infra/postgres/init.sql" in v for v in postgres["volumes"])
    assert "pg_isready" in " ".join(postgres["healthcheck"]["test"])
    init = (REPO_ROOT / "infra" / "postgres" / "init.sql").read_text()
    for extension in ("vector", "unaccent"):
        assert f"CREATE EXTENSION IF NOT EXISTS {extension};" in init


@pytest.mark.parametrize("name", ["postgres", "neo4j"])
def test_databases_are_in_the_lite_profile(name: str) -> None:
    assert services()[name]["profiles"] == ["lite"]


def test_dev_containers_start_without_a_profile() -> None:
    for name in ("mentormind", "vlm-server"):
        assert "profiles" not in services()[name], name


def test_vlm_server_is_ollama_on_one_gpu_with_a_configurable_image_floor() -> None:
    vlm = services()["vlm-server"]
    assert vlm["build"]["dockerfile"] == "docker/Dockerfile.ollama"
    assert default(vlm["environment"]["VLM_SERVER_OLLAMA_MODEL"]) == "qwen3-vl:8b"
    assert int(default(vlm["environment"]["VLM_SERVER_IMAGE_MIN_TOKENS"])) < 1024  # Ollama alone: 1024
    assert int(default(vlm["environment"]["VLM_SERVER_CONTEXT_LENGTH"])) >= 32768
    [device] = vlm["deploy"]["resources"]["reservations"]["devices"]
    assert len(device["device_ids"]) == 1


def test_mentormind_calls_the_vlm_server_over_a_local_url() -> None:
    url = default(services()["mentormind"]["environment"]["KNOWHOW_VLM_BASE_URL"])
    assert url == "http://vlm-server:11434/v1"
    assert is_private_url(url)  # counts as self-hosted: factory data may be sent


def test_published_ports_bind_loopback_only() -> None:
    for name, service in services().items():
        for port in service.get("ports", []):
            assert str(port).startswith("127.0.0.1:"), (name, port)


def test_overrides_live_in_infra_docker_and_merge_into_the_root_file() -> None:
    """One compose file at the root; every machine-specific override under infra/docker/."""
    root_files = sorted(p.name for p in REPO_ROOT.glob("docker-compose*.yml"))
    assert root_files == ["docker-compose.yml"]
    overrides = sorted(p.name for p in (REPO_ROOT / "infra" / "docker").glob("docker-compose*.yml"))
    assert overrides == [
        "docker-compose.cdi.yml",
        "docker-compose.devbox.yml",
        "docker-compose.rocm.yml",
    ]
    for name in overrides:
        data = load(OVERRIDES_DIR / name)
        # An override only patches services the base file defines; it never invents one.
        assert set(data["services"]) <= set(services()), name


def test_rocm_override_gives_the_vlm_server_one_amd_gcd() -> None:
    """spec 04 FR-08 on AMD: device nodes instead of the nvidia driver, still exactly one GPU."""
    vlm = load(OVERRIDES_DIR / "docker-compose.rocm.yml")["services"]["vlm-server"]
    assert vlm["build"]["args"]["BASE"].endswith("-rocm")
    assert set(vlm["devices"]) == {"/dev/kfd", "/dev/dri"}
    assert default(vlm["environment"]["ROCR_VISIBLE_DEVICES"]) == "0"
