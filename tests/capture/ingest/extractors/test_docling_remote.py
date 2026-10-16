"""spec 02 FR-02c / AC-19, AC-21 — Docling on the team's inference server (``KNOWHOW_DOC_EXTRACTOR=remote``).

The server is a ``httpx.MockTransport`` answering ``export_to_dict()`` of a real ``DoclingDocument``
(constitution art. 6: no network, no Docling models in tests).
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from mentormind.capture.ingest import cli as ingest_cli
from mentormind.capture.ingest.extractors.base import ExtractorError
from mentormind.capture.ingest.extractors.docling import DoclingExtractor, docling_to_raw
from mentormind.capture.ingest.extractors.docling_remote import RemoteDoclingExtractor
from mentormind.capture.ingest.extractors.mmore import MmoreFastExtractor
from mentormind.capture.ingest.pipeline import ingest_file, ingest_path
from mentormind.capture.ingest.select import extract_with_fallback
from mentormind.capture.ingest.tokens import WhitespaceTokenCounter
from mentormind.core.cli import app
from mentormind.core.config import Settings, get_settings
from mentormind.core.guard import ConfidentialDataError
from mentormind.core.providers.errors import ProviderConfigError
from mentormind.core.schemas import DataClassification
from tests.capture.ingest.fakes import FakeExtractor
from tests.core.providers.inference.fakes import PRIVATE_URL, PUBLIC_URL, FakeInferenceServer, multipart

CONFIDENTIAL = DataClassification.FACTORY_CONFIDENTIAL


def sop_document() -> Any:
    """A two-page DoclingDocument: heading, text, list, table, picture with OCR text, caption, footer."""
    doc_module = pytest.importorskip("docling_core.types.doc")

    def prov(page: int) -> Any:
        bbox = doc_module.BoundingBox(l=0, t=0, r=10, b=10)
        return doc_module.ProvenanceItem(page_no=page, bbox=bbox, charspan=(0, 1))

    label = doc_module.DocItemLabel
    doc = doc_module.DoclingDocument(name="sop")
    for page in (1, 2):
        doc.add_page(page_no=page, size=doc_module.Size(width=595, height=842))
    doc.add_heading(text="Đóng gói", level=1, prov=prov(1))
    doc.add_text(label=label.TEXT, text="Đặt linh kiện PACK01.", prov=prov(1))
    doc.add_list_item(text="Kiểm tra lot", parent=doc.add_list_group(), prov=prov(2))
    cells = [
        doc_module.TableCell(
            text=text,
            start_row_offset_idx=r,
            end_row_offset_idx=r + 1,
            start_col_offset_idx=c,
            end_col_offset_idx=c + 1,
            column_header=r == 0,
        )
        for r, row in enumerate([["a", "b"], ["1", "2"]])
        for c, text in enumerate(row)
    ]
    doc.add_table(data=doc_module.TableData(num_rows=2, num_cols=2, table_cells=cells), prov=prov(2))
    picture = doc.add_picture(prov=prov(2))
    doc.add_text(label=label.TEXT, text="TN057763-7131", parent=picture, prov=prov(2))
    doc.add_text(label=label.CAPTION, text="Hình 1: nhãn", prov=prov(2))
    doc.add_text(label=label.PAGE_FOOTER, text="trang 1", prov=prov(1))
    return doc


def pdf(tmp_path: Path, name: str = "sop.pdf") -> Path:
    path = tmp_path / name
    path.write_bytes(b"%PDF-1.7 bytes")
    return path


def converting(document: Any) -> FakeInferenceServer:
    body = {"filename": "sop.pdf", "num_pages": 2, "document": document.export_to_dict()}
    return FakeInferenceServer({"/documents/convert": body})


def test_ac_19_remote_gives_the_same_raw_document_as_local_docling(tmp_path: Path) -> None:
    document = sop_document()
    server = converting(document)
    path = pdf(tmp_path)
    raw = RemoteDoclingExtractor(server.client(api_key="tok")).extract(path)
    assert raw == docling_to_raw(document, path)  # the same mapping as DoclingExtractor
    kinds = [b.kind.value for b in raw.blocks]
    assert kinds == ["text", "text", "text", "table", "drawing_note", "figure_caption"]
    assert raw.extractor == "docling" and raw.num_pages == 2
    [request] = server.requests
    assert str(request.url) == f"{PRIVATE_URL}/documents/convert" and request.headers["Authorization"] == "Bearer tok"
    assert multipart(request) == ({}, {"file": ("sop.pdf", b"%PDF-1.7 bytes")})


def test_ac_19_a_server_failure_falls_back_like_a_local_docling_failure(tmp_path: Path) -> None:
    server = FakeInferenceServer({"/documents/convert": httpx.Response(422, json={"error": "PDF hỏng"})})
    mmore = FakeExtractor("mmore")
    raw, reasons = extract_with_fallback(pdf(tmp_path), [RemoteDoclingExtractor(server.client()), mmore])
    assert raw.extractor == "mmore" and mmore.calls == 1
    [reason] = reasons
    assert reason.startswith("docling-remote:") and "422" in reason and "PDF hỏng" in reason
    malformed = FakeInferenceServer({"/documents/convert": {"filename": "sop.pdf"}})
    with pytest.raises(ExtractorError, match="document"):
        RemoteDoclingExtractor(malformed.client()).extract(pdf(tmp_path))


def test_ac_19_without_docling_core_the_error_says_how(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server = converting(sop_document())

    def no_docling_core(name: str) -> Any:
        raise ImportError(name)

    monkeypatch.setattr(importlib, "import_module", no_docling_core)
    with pytest.raises(ExtractorError, match="docling-core.*extra `ingest`"):
        RemoteDoclingExtractor(server.client()).extract(pdf(tmp_path))


def test_ac_19_settings_pick_remote_docling_and_keep_the_mmore_fallback() -> None:
    remote, fallback = ingest_cli.build_extractors(
        Settings(_env_file=None, doc_extractor="remote", inference_url=PRIVATE_URL)
    )
    assert isinstance(remote, RemoteDoclingExtractor) and isinstance(fallback, MmoreFastExtractor)
    assert remote.is_cloud is False and remote.supports(Path("a.XLSX")) and not remote.supports(Path("a.txt"))
    # Explicit: a KNOWHOW_DOC_EXTRACTOR exported from .env (dev container) must not decide this case.
    local, _ = ingest_cli.build_extractors(Settings(_env_file=None, doc_extractor="docling"))
    assert isinstance(local, DoclingExtractor)
    with pytest.raises(ProviderConfigError, match="KNOWHOW_INFERENCE_URL"):
        ingest_cli.build_extractors(Settings(_env_file=None, doc_extractor="remote", inference_url=None))


def test_ac_21_cloud_url_refuses_factory_documents_before_any_upload(tmp_path: Path) -> None:
    server = converting(sop_document())
    extractors = [RemoteDoclingExtractor(server.client(PUBLIC_URL)), FakeExtractor("mmore")]
    out = tmp_path / "out"
    kwargs: dict[str, Any] = {
        "extractors": extractors,
        "counter": WhitespaceTokenCounter(),
        "settings": Settings(_env_file=None),
    }
    with pytest.raises(ConfidentialDataError):
        ingest_path(pdf(tmp_path), CONFIDENTIAL, out, **kwargs)
    with pytest.raises(ConfidentialDataError):
        ingest_file(pdf(tmp_path), CONFIDENTIAL, out, **kwargs)
    assert server.requests == [] and not out.exists()
    [result] = ingest_path(pdf(tmp_path), DataClassification.PUBLIC, out, **kwargs)
    assert result.error is None and result.chunks > 0 and len(server.requests) == 1


def test_ac_21_cli_reports_a_missing_url_or_a_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOWHOW_DOC_EXTRACTOR", "remote")
    monkeypatch.setenv("KNOWHOW_TOKEN_COUNTER", "whitespace")
    monkeypatch.setenv("KNOWHOW_INFERENCE_URL", "")  # empty beats a value in a developer's .env
    monkeypatch.setenv("KNOWHOW_LOCAL_HOSTS", "[]")
    get_settings.cache_clear()
    try:
        args = ["ingest", "run", "--input", str(pdf(tmp_path)), "--out", str(tmp_path / "out")]
        result = CliRunner().invoke(app, [*args, "--classification", "public"])
        assert result.exit_code == 2 and "KNOWHOW_INFERENCE_URL" in result.output
        monkeypatch.setenv("KNOWHOW_INFERENCE_URL", "https://inference.example.com/v1")
        get_settings.cache_clear()
        result = CliRunner().invoke(app, [*args, "--classification", "factory_confidential"])
        assert result.exit_code == 2 and "factory_confidential" in result.output
        assert not (tmp_path / "out").exists()
    finally:
        get_settings.cache_clear()
