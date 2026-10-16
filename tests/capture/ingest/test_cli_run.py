"""spec 02 FR-01/08, AC-05, AC-08, AC-09 — `knowhow ingest run`."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from mentormind.capture.ingest import cli as ingest_cli
from mentormind.capture.ingest.extractors.base import ExtractorError
from mentormind.capture.ingest.jsonl import read_chunks
from mentormind.capture.ingest.tokens import WhitespaceTokenCounter
from mentormind.core.cli import app
from tests.capture.ingest.fakes import FakeExtractor, raw_doc

runner = CliRunner()


@pytest.fixture(autouse=True)
def fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ingest_cli, "build_extractors", lambda settings: [FakeExtractor("docling", doc=raw_doc(blocks=2))]
    )
    monkeypatch.setattr(ingest_cli, "build_counter", lambda settings: WhitespaceTokenCounter())


def _args(src: Path, out: Path, *extra: str) -> list[str]:
    return ["ingest", "run", "--input", str(src), "--out", str(out), *extra]


def _pdf(tmp_path: Path, name: str = "a.pdf", content: bytes = b"x") -> Path:
    f = tmp_path / name
    f.write_bytes(content)
    return f


def test_ac_05_cli_classification_written(tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = runner.invoke(app, _args(_pdf(tmp_path), out, "--classification", "factory_confidential"))
    assert result.exit_code == 0, result.output
    [jsonl] = out.glob("*.jsonl")
    assert {c.data_classification.value for _, c in read_chunks(jsonl)} == {"factory_confidential"}


def test_fr_08_summary_line_per_file_and_total(tmp_path: Path) -> None:
    result = runner.invoke(app, _args(_pdf(tmp_path), tmp_path / "out", "--classification", "public"))
    assert "docling" in result.output and "chunk" in result.output and "DOC-" in result.output


def test_ac_08_missing_classification_errors_no_file(tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = runner.invoke(app, _args(_pdf(tmp_path), out))
    assert result.exit_code != 0 and not out.exists()


def test_ac_08_invalid_classification_errors_no_file(tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = runner.invoke(app, _args(_pdf(tmp_path), out, "--classification", "secret"))
    assert result.exit_code != 0 and not out.exists()


def test_ac_09_reingest_other_label_errors_then_force(tmp_path: Path) -> None:
    src, out = _pdf(tmp_path), tmp_path / "out"
    assert runner.invoke(app, _args(src, out, "--classification", "public")).exit_code == 0
    clash = runner.invoke(app, _args(src, out, "--classification", "synthetic"))
    assert clash.exit_code != 0 and "--force" in clash.output
    assert runner.invoke(app, _args(src, out, "--classification", "synthetic", "--force")).exit_code == 0


def test_one_file_failure_others_continue_exit_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = tmp_path / "in"
    src.mkdir()
    _pdf(src, "a.pdf", b"1")
    _pdf(src, "b.pdf", b"2")

    class Flaky(FakeExtractor):
        def extract(self, path: Path):
            if path.name == "a.pdf":
                raise ExtractorError("bad a")
            return super().extract(path)

    monkeypatch.setattr(ingest_cli, "build_extractors", lambda settings: [Flaky("docling", doc=raw_doc(blocks=2))])
    out = tmp_path / "out"
    result = runner.invoke(app, _args(src, out, "--classification", "public"))
    assert result.exit_code == 1 and "bad a" in result.output and len(list(out.glob("*.jsonl"))) == 1


def test_missing_input_is_a_clear_error(tmp_path: Path) -> None:
    result = runner.invoke(app, _args(tmp_path / "nope", tmp_path / "out", "--classification", "public"))
    assert result.exit_code != 0 and "nope" in result.output
