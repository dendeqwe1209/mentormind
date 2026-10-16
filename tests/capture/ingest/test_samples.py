"""spec 02 AC-01, AC-02, AC-03 — real Docling on `data/samples/docs/`.

Slow (about 50 s on CPU, loads OCR models), so it runs only with ``KNOWHOW_RUN_SAMPLE_TESTS=1``:
``KNOWHOW_RUN_SAMPLE_TESTS=1 uv run pytest tests/capture/ingest/test_samples.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mentormind.capture.ingest.cli import build_counter, build_extractors
from mentormind.capture.ingest.jsonl import read_chunks
from mentormind.capture.ingest.pipeline import ingest_path
from mentormind.core.config import get_settings
from mentormind.core.schemas import ChunkKind, DataClassification, DocumentChunk

SAMPLES = Path(__file__).resolve().parents[3] / "data" / "samples" / "docs"

pytestmark = pytest.mark.skipif(
    os.environ.get("KNOWHOW_RUN_SAMPLE_TESTS") != "1" or not SAMPLES.is_dir(),
    reason="slow OCR test: set KNOWHOW_RUN_SAMPLE_TESTS=1 and provide data/samples/docs/",
)


@pytest.fixture(scope="module")
def chunks_by_file(tmp_path_factory: pytest.TempPathFactory) -> dict[str, list[DocumentChunk]]:
    out = tmp_path_factory.mktemp("chunks")
    settings = get_settings()
    ingest_path(
        SAMPLES,
        DataClassification.SYNTHETIC,
        out,
        extractors=build_extractors(settings),
        counter=build_counter(settings),
        settings=settings,
    )
    by_file: dict[str, list[DocumentChunk]] = {}
    for jsonl in sorted(out.glob("*.jsonl")):
        chunks = [chunk for _, chunk in read_chunks(jsonl)]
        by_file[Path(chunks[0].source_path).name] = chunks
    return by_file


def test_ac_01_three_samples_all_produce_chunks(chunks_by_file: dict[str, list[DocumentChunk]]) -> None:
    for name in ("packing_sop.pdf", "packing_sop_scan.pdf", "sps_form_12_1_14.xlsx"):
        assert chunks_by_file.get(name), f"{name} produced no chunk"


def test_ac_02_xlsx_values_survive_as_table_chunks(chunks_by_file: dict[str, list[DocumentChunk]]) -> None:
    # Proposal 3A: the sample is a form, not a rectangular table, so check label/value pairs.
    chunks = chunks_by_file["sps_form_12_1_14.xlsx"]
    assert {c.kind for c in chunks} == {ChunkKind.TABLE}
    assert all("---" in c.text for c in chunks)
    assert "AA123456-7890" in " ".join(c.text for c in chunks)


def test_ac_03_scanned_pdf_goes_through_docling_ocr(chunks_by_file: dict[str, list[DocumentChunk]]) -> None:
    chunks = chunks_by_file["packing_sop_scan.pdf"]
    assert {c.extractor for c in chunks} == {"docling"}
    assert "PACK01" in " ".join(c.text for c in chunks)
    assert any("PACK01" in c.process_ids for c in chunks)


def test_ac_03_image_only_pages_of_doc_04_are_read_by_ocr(tmp_path: Path) -> None:
    doc_04 = SAMPLES.parent.parent / "6-7 NASWEB Supplier-Label-Tech Spec.pdf"
    if not doc_04.is_file():
        pytest.skip("DOC-04 is not in data/ (public file, not redistributed in the repo)")
    settings = get_settings()
    ingest_path(
        doc_04,
        DataClassification.PUBLIC,
        tmp_path,
        extractors=build_extractors(settings),
        counter=build_counter(settings),
        settings=settings,
    )
    chunks = [chunk for jsonl in tmp_path.glob("*.jsonl") for _, chunk in read_chunks(jsonl)]
    page_3 = " ".join(c.text for c in chunks if c.page == 3)
    assert "TN057763-7131" in page_3  # the part number printed inside the label drawing
    assert any(c.kind is ChunkKind.DRAWING_NOTE and c.page == 3 for c in chunks)
    assert {c.extractor for c in chunks} == {"docling"}
