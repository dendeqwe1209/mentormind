"""Static checks of ``infra/postgres/init.sql`` against the contract and constitution.

They run without Docker (constitution art. 6); the schema itself was applied to
``pgvector/pgvector:pg16`` when it changed (spec 01 changelog v1.12).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INIT = (REPO / "infra" / "postgres" / "init.sql").read_text(encoding="utf-8")
CONTRACT = json.loads((REPO / "docs" / "contracts" / "work_profile.schema.json").read_text(encoding="utf-8"))


def _table(name: str) -> str:
    match = re.search(rf"create table if not exists public\.{name} \((.*?)\n\);", INIT, re.DOTALL)
    assert match, f"table {name} missing"
    return match.group(1)


def test_classification_is_the_constitution_vocabulary() -> None:
    assert "check (value in ('public', 'synthetic', 'factory_confidential'))" in INIT
    assert "'public','internal','confidential','restricted'" not in INIT
    columns = re.findall(r"^\s+data_classification (.+)$", INIT, re.MULTILINE)
    assert columns and all(c.startswith("public.data_classification") for c in columns)


def test_reason_source_only_from_the_expert() -> None:
    assert "model_inference" not in INIT
    allowed = [v for v in CONTRACT["properties"]["reason_source"]["enum"] if v]
    assert f"reason_source in ('{allowed[0]}','{allowed[1]}')" in _table("knowledge_units")


def test_knowledge_units_has_every_contract_field() -> None:
    table = _table("knowledge_units")
    split = {"expert": "expert_id", "review": "reviewer"}
    for field in CONTRACT["properties"]:
        column = split.get(field, field)
        assert re.search(rf"^\s+{column} ", table, re.MULTILINE), f"no column for {field}"
    generated_by = CONTRACT["properties"]["generated_by"]["enum"]
    assert f"generated_by in ('{generated_by[0]}','{generated_by[1]}','{generated_by[2]}')" in table


def test_contract_rules_are_check_constraints() -> None:
    for name in ("vlm_draft_has_no_reason", "reason_has_expert_source", "approved_is_attributed"):
        assert f"constraint {name}" in _table("knowledge_units")
    assert "constraint reject_has_comment" in _table("knowledge_reviews")


def test_one_vector_table_with_the_spec_filters() -> None:
    table = _table("knowhow_chunks")
    for column in ("chunk_id", "source_type", "kind", "process_ids", "data_classification"):
        assert re.search(rf"^\s+{column} ", table, re.MULTILINE)
    assert len(re.findall(r"^\s+embedding vector", INIT, re.MULTILINE)) == 1  # one vector path


def test_full_text_uses_unaccent() -> None:
    assert "with public.unaccent, pg_catalog.simple" in INIT
    assert "to_tsvector('simple'" not in INIT


def test_only_approved_profiles_are_indexed() -> None:
    assert "trg_chunks_only_approved" in INIT
    assert "trg_knowledge_unindex" in INIT
