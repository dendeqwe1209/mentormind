"""mmore fast adapter (degraded text-only path, proposal 5); parses the T02-0 spike output."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from mentormind.capture.ingest.extractors.base import ExtractorError
from mentormind.capture.ingest.extractors.mmore import MmoreFastExtractor, parse_mmore_record
from mentormind.core.schemas import ChunkKind

FIXTURE = Path(__file__).parents[3] / "fixtures" / "ingest" / "mmore_fast_packing_sop.json"


def test_parse_mmore_fast_record_splits_text_by_page() -> None:
    raw = parse_mmore_record(json.loads(FIXTURE.read_text()), Path("packing_sop.pdf"))
    assert raw.extractor == "mmore" and raw.metadata["degraded"] is True
    assert raw.num_pages == 3 and [b.page for b in raw.blocks] == [1, 2, 3]
    assert all(b.kind is ChunkKind.TEXT and b.text.strip() for b in raw.blocks)
    assert raw.blocks[0].text.startswith("QUY TRÌNH THAO TÁC CHUẨN")


def test_record_without_paragraph_starts_is_one_unpaged_block() -> None:
    raw = parse_mmore_record({"text": "hello", "metadata": {}}, Path("a.pdf"))
    assert [(b.page, b.text) for b in raw.blocks] == [(None, "hello")]


def test_supports_pdf_only() -> None:
    ex = MmoreFastExtractor()
    assert ex.supports(Path("a.pdf")) and not ex.supports(Path("a.xlsx"))


def test_missing_binary_raises_extractor_error(tmp_path: Path) -> None:
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with pytest.raises(ExtractorError, match="mmore"):
        MmoreFastExtractor(binary="/nonexistent/mmore").extract(pdf)


def test_subprocess_failure_raises_with_stderr(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    def run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 2, stdout="", stderr="traceback: kaboom")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(ExtractorError, match="kaboom"):
        MmoreFastExtractor().extract(pdf)
