"""spec 02 FR-02 (proposal 5), AC-03, AC-11 — extractor choice and fallback."""

from __future__ import annotations

from pathlib import Path

import pytest

from mentormind.capture.ingest.extractors.base import ExtractorError
from mentormind.capture.ingest.select import extract_with_fallback
from tests.capture.ingest.fakes import FakeExtractor, raw_doc

PDF, XLSX = Path("a.pdf"), Path("a.XLSX")
OFFICE = (".pdf", ".docx", ".xlsx", ".pptx")


def test_primary_extractor_used_when_it_works() -> None:
    docling, mmore = FakeExtractor("docling", suffixes=OFFICE), FakeExtractor("mmore")
    doc, reasons = extract_with_fallback(PDF, [docling, mmore])
    assert doc.extractor == "docling" and reasons == [] and mmore.calls == 0


def test_ac_11_docling_failure_falls_back_to_mmore() -> None:
    docling = FakeExtractor("docling", raises=ExtractorError("boom"))
    mmore = FakeExtractor("mmore", doc=raw_doc("mmore"))
    doc, reasons = extract_with_fallback(PDF, [docling, mmore])
    assert doc.extractor == "mmore"
    assert len(reasons) == 1 and reasons[0].startswith("docling:") and "boom" in reasons[0]


def test_zero_blocks_counts_as_failure() -> None:
    docling = FakeExtractor("docling", doc=raw_doc("docling", blocks=0))
    mmore = FakeExtractor("mmore", doc=raw_doc("mmore"))
    doc, reasons = extract_with_fallback(PDF, [docling, mmore])
    assert doc.extractor == "mmore" and "0 khối" in reasons[0]


def test_ac_11_all_extractors_fail_raises_with_every_reason() -> None:
    chain = [
        FakeExtractor("docling", raises=ExtractorError("d-fail")),
        FakeExtractor("mmore", raises=ExtractorError("m-fail")),
    ]
    with pytest.raises(ExtractorError) as err:
        extract_with_fallback(PDF, chain)
    assert "d-fail" in str(err.value) and "m-fail" in str(err.value)


def test_office_file_has_no_fallback_to_pdf_only_extractor() -> None:
    docling = FakeExtractor("docling", suffixes=OFFICE, raises=ExtractorError("d-fail"))
    mmore = FakeExtractor("mmore")  # supports only .pdf
    with pytest.raises(ExtractorError, match="d-fail"):
        extract_with_fallback(XLSX, [docling, mmore])
    assert mmore.calls == 0


def test_unsupported_suffix_raises() -> None:
    with pytest.raises(ExtractorError, match="không extractor nào hỗ trợ"):
        extract_with_fallback(Path("a.txt"), [FakeExtractor("docling")])


def test_unexpected_exception_is_not_swallowed() -> None:
    with pytest.raises(KeyError):
        extract_with_fallback(PDF, [FakeExtractor("docling", raises=KeyError("bug")), FakeExtractor("mmore")])
