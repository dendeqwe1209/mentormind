"""``knowhow ingest ...`` (spec 02 FR-01, FR-08)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from mentormind.capture.ingest.extractors.base import Extractor
from mentormind.capture.ingest.extractors.docling import DoclingExtractor
from mentormind.capture.ingest.extractors.docling_remote import RemoteDoclingExtractor
from mentormind.capture.ingest.extractors.mmore import MmoreFastExtractor
from mentormind.capture.ingest.index import DOC_ID, index_chunks, replace_docs
from mentormind.capture.ingest.pipeline import IngestResult, ingest_path
from mentormind.capture.ingest.tokens import BgeM3TokenCounter, TokenCounter, WhitespaceTokenCounter
from mentormind.core.config import Settings, get_settings
from mentormind.core.guard.data_guard import ConfidentialDataError
from mentormind.core.providers.errors import ProviderConfigError
from mentormind.core.schemas import DataClassification
from mentormind.knowledge_base.store.vector_store import VectorStore, VectorStoreError, get_vector_store

app = typer.Typer(help="Ingest tài liệu PDF/DOCX/XLSX/PPTX thành chunk (spec 02).", no_args_is_help=True)


def build_extractors(settings: Settings) -> list[Extractor]:
    """Docling first — here, or on the inference server (FR-02c); mmore fast is the degraded PDF fallback (FR-02).

    Raises:
        ProviderConfigError: ``KNOWHOW_DOC_EXTRACTOR=remote`` without ``KNOWHOW_INFERENCE_URL``.
    """
    docling: Extractor = (
        RemoteDoclingExtractor.from_settings(settings) if settings.doc_extractor == "remote" else DoclingExtractor()
    )
    return [docling, MmoreFastExtractor(binary=settings.mmore_bin)]


def build_counter(settings: Settings) -> TokenCounter:
    if settings.token_counter == "whitespace":
        return WhitespaceTokenCounter()
    return BgeM3TokenCounter(settings.embed_model)


def build_store(settings: Settings) -> VectorStore:
    return get_vector_store(settings)


@app.command("run", help="Đọc tài liệu, tách chunk và ghi JSONL (mỗi file nguồn một <doc_id>.jsonl).")
def run_cmd(
    input_: Annotated[Path, typer.Option("--input", help="File hoặc thư mục tài liệu.")],
    classification: Annotated[
        DataClassification,
        typer.Option("--classification", case_sensitive=False, help="Nhãn dữ liệu bắt buộc, áp cho mọi chunk."),
    ],
    out: Annotated[Path, typer.Option("--out", help="Thư mục ghi JSONL.")] = Path("data/work/chunks"),
    force: Annotated[bool, typer.Option("--force", help="Ghi đè kể cả khi đổi nhãn.")] = False,
) -> None:
    settings = get_settings()
    try:
        results = ingest_path(
            input_,
            classification,
            out,
            extractors=build_extractors(settings),
            counter=build_counter(settings),
            settings=settings,
            force=force,
        )
    except (FileNotFoundError, ConfidentialDataError, ProviderConfigError) as exc:
        typer.echo(f"Lỗi: {exc}", err=True)
        raise typer.Exit(2) from exc
    for result in results:
        typer.echo(_line(result))
    failed = [r for r in results if r.error]
    done = [r for r in results if not r.error and not r.skipped]
    typer.echo(
        f"Tổng: {len(done)} file xong, {sum(r.chunks for r in done)} chunk, "
        f"{sum(r.skipped for r in results)} bỏ qua, {len(failed)} lỗi."
    )
    if failed:
        raise typer.Exit(1)


def _line(r: IngestResult) -> str:
    if r.skipped:
        return f"{r.path} | skipped (định dạng không hỗ trợ)"
    if r.error:
        return f"{r.path} | LỖI: {r.error}"
    note = f" | chuyển extractor: {'; '.join(r.reasons)}" if r.reasons else ""
    warn = (
        f" | CẢNH BÁO text layer nghi sai mã hóa ở trang {', '.join(map(str, r.suspect_pages))}"
        if r.suspect_pages
        else ""
    )
    return f"{r.doc_id} | {r.extractor} | {r.pages} trang | {r.chunks} chunk | {r.seconds:.1f}s{note}{warn}"


@app.command("index", help="Embed chunk trong thư mục JSONL và upsert vào vector store (lọc được theo nhãn dữ liệu).")
def index_cmd(
    chunks: Annotated[Path, typer.Option("--chunks", help="Thư mục chứa các <doc_id>.jsonl.")] = Path(
        "data/work/chunks"
    ),
    batch_size: Annotated[int, typer.Option("--batch-size", min=1, help="Số chunk mỗi lần upsert.")] = 32,
    replace_doc: Annotated[
        list[str] | None,
        typer.Option(
            "--replace-doc",
            help="doc_id cũ cần xóa sau khi index xong (file nguồn đã đổi nên doc_id mới). Lặp lại được.",
        ),
    ] = None,
) -> None:
    for doc_id in replace_doc or []:
        if not DOC_ID.fullmatch(doc_id):
            typer.echo(f"Lỗi: --replace-doc {doc_id!r} không phải doc_id (dạng DOC-<12 ký tự hex>).", err=True)
            raise typer.Exit(2)
    settings = get_settings()
    try:
        store = build_store(settings)
        result = index_chunks(chunks, store, batch_size=batch_size)
        failed = bool(result.files_failed)
        removed = {} if failed else replace_docs(store, replace_doc or [], keep=result.doc_ids)
    except (FileNotFoundError, VectorStoreError) as exc:
        typer.echo(f"Lỗi: {exc}", err=True)
        raise typer.Exit(2) from exc
    for name, why in result.files_failed:
        typer.echo(f"{name} | LỖI, không ghi gì: {why}")
    typer.echo(
        f"Tổng: {result.upserted} chunk đã upsert từ {result.files_ok} file, {len(result.files_failed)} file lỗi."
    )
    for doc_id, count in removed.items():
        why = " (bỏ qua: vừa index trong lần chạy này)" if doc_id in result.doc_ids else ""
        typer.echo(f"{doc_id} | đã xóa {count} chunk cũ{why}")
    if failed:
        if replace_doc:
            typer.echo("Không xóa chunk cũ vì có file lỗi.", err=True)
        raise typer.Exit(1)
