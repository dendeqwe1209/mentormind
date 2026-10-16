"""spec 02 §3 / 02b §4.1 — DocumentChunk model and its validators."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from mentormind.core.schemas import ChunkKind, DataClassification, DocumentChunk

TABLE = "| a | b |\n| --- | --- |\n| 1 | 2 |"


def _chunk(**over: Any) -> DocumentChunk:
    base: dict[str, Any] = {
        "chunk_id": "DOC-0123456789ab#p1-0",
        "doc_id": "DOC-0123456789ab",
        "source_path": "data/samples/docs/x.pdf",
        "title": None,
        "page": 1,
        "kind": ChunkKind.TEXT,
        "text": "hello",
        "data_classification": DataClassification.PUBLIC,
        "extractor": "mmore",
    }
    base.update(over)
    return DocumentChunk(**base)


def test_ac_01_valid_chunk_defaults() -> None:
    c = _chunk()
    assert c.source_type == "document"
    assert c.process_ids == [] and c.part_numbers == [] and c.metadata == {}


@pytest.mark.parametrize("bad", ["DOC-1#p1-0", "DOC-0123456789ab#1-0", "x", "DOC-0123456789ab#p1"])
def test_chunk_id_pattern_rejected(bad: str) -> None:
    with pytest.raises(ValidationError):
        _chunk(chunk_id=bad)


@pytest.mark.parametrize("text", ["", "   \n"])
def test_empty_text_rejected(text: str) -> None:
    with pytest.raises(ValidationError):
        _chunk(text=text)


def test_table_kind_requires_markdown_table() -> None:
    assert _chunk(kind=ChunkKind.TABLE, text=TABLE).kind is ChunkKind.TABLE
    with pytest.raises(ValidationError):
        _chunk(kind=ChunkKind.TABLE, text="just prose")


def test_codes_are_deduplicated_and_sorted() -> None:
    c = _chunk(process_ids=["PACK02", "PACK01", "PACK02"], part_numbers=["B-2", "A-1", "B-2"])
    assert c.process_ids == ["PACK01", "PACK02"]
    assert c.part_numbers == ["A-1", "B-2"]


def test_classification_required_and_enum_checked() -> None:
    with pytest.raises(ValidationError):
        _chunk(data_classification="secret")


def test_extractor_enum_checked() -> None:
    with pytest.raises(ValidationError):
        _chunk(extractor="tesseract")


def test_json_roundtrip_is_stable() -> None:
    c = _chunk(kind=ChunkKind.TABLE, text=TABLE, process_ids=["PACK01"])
    assert DocumentChunk.model_validate_json(c.model_dump_json()) == c
