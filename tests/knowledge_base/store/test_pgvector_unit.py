"""spec 02b §5 — pure parts of the pgvector backend (no database needed)."""

from __future__ import annotations

import pytest

from mentormind.core.schemas.common import DataClassification
from mentormind.knowledge_base.store.pgvector_store import (
    build_where,
    check_dimension,
    quote_table,
    vector_literal,
)
from mentormind.knowledge_base.store.vector_store import (
    FilterClause,
    VectorStoreError,
    parse_filters,
)


def test_parse_filters_scalar_list_enum_and_alias() -> None:
    clauses = parse_filters(
        {
            "kind": "table",
            "data_classification": [DataClassification.PUBLIC, "synthetic"],
            "doc_id": "DOC-1",
            "process_ids": "PACK01",
            "part_number": ["A-1"],
        }
    )
    assert clauses == [
        FilterClause("kind", ["table"], False),
        FilterClause("data_classification", ["public", "synthetic"], False),
        FilterClause("ref_id", ["DOC-1"], False),
        FilterClause("process_ids", ["PACK01"], True),
        FilterClause("part_numbers", ["A-1"], True),
    ]


def test_parse_filters_rejects_unknown_key() -> None:
    with pytest.raises(ValueError, match="Filter không hỗ trợ"):
        parse_filters({"text; DROP TABLE x": "1"})


def test_build_where_is_parameterised_and_empty_list_matches_nothing() -> None:
    sql, params = build_where(
        [
            FilterClause("kind", ["table"], False),
            FilterClause("process_ids", ["PACK01", "SOLD12"], True),
            FilterClause("data_classification", [], False),
        ]
    )
    text = sql.as_string()
    assert "PACK01" not in text and "table" not in text  # values travel as parameters
    assert '"kind" = ANY(%(f0)s)' in text and '"process_ids" && %(f1)s::text[]' in text and "FALSE" in text
    assert params == {"f0": ["table"], "f1": ["PACK01", "SOLD12"]}


def test_build_where_without_filters_is_true() -> None:
    sql, params = build_where([])
    assert sql.as_string() == "TRUE" and params == {}


def test_vector_literal() -> None:
    assert vector_literal([0.5, -1.0, 0.0]) == "[0.5,-1.0,0.0]"


@pytest.mark.parametrize("name", ["knowhow_chunks", "_t1", "A"])
def test_valid_table_names(name: str) -> None:
    assert quote_table(name).as_string() == f'"{name}"'


@pytest.mark.parametrize("name", ["", "1abc", "a;drop", 'a"b', "a b", "x" * 64, "public.knowhow_chunks"])
def test_invalid_table_names_are_rejected(name: str) -> None:
    with pytest.raises(VectorStoreError, match="KNOWHOW_VECTOR_TABLE"):
        quote_table(name)


def test_ac_16_dimension_mismatch_is_a_clear_error() -> None:
    check_dimension(1024, 1024)
    with pytest.raises(VectorStoreError, match=r"vector\(1024\).*256"):
        check_dimension(1024, 256)
    with pytest.raises(VectorStoreError, match="không khai báo"):
        check_dimension(-1, 1024)
