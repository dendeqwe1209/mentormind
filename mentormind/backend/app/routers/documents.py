"""Indexed documents: list them, delete one (spec 08 §2 "Xoá dữ liệu", AC-23).

The list is read from ``<work_dir>/chunks/<doc_id>.jsonl``, the files ``POST /ingest/documents`` and
``knowhow ingest run`` write and ``knowhow ingest index`` reads: ``VectorStore`` has no listing
operation, and these files exist whatever the vector backend.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

from mentormind.backend.app.deps import VectorStoreOpener, get_vector_store_opener
from mentormind.capture.ingest.index import DOC_ID
from mentormind.capture.ingest.jsonl import ChunkFileError, read_chunks
from mentormind.capture.ingest.pipeline import SUPPORTED_SUFFIXES, doc_id_for
from mentormind.core.config import get_settings
from mentormind.core.schemas import DocumentDeleteResult, DocumentInfo

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[DocumentInfo])
def list_documents() -> list[DocumentInfo]:
    chunks_dir = get_settings().work_dir / "chunks"
    if not chunks_dir.is_dir():
        return []
    documents = [_info(path) for path in chunks_dir.glob("*.jsonl") if DOC_ID.fullmatch(path.stem)]
    return sorted(documents, key=lambda d: (d.name.lower(), d.doc_id))


@router.delete("/{doc_id}", response_model=DocumentDeleteResult)
def delete_document(
    doc_id: str, open_vectors: VectorStoreOpener = Depends(get_vector_store_opener)
) -> DocumentDeleteResult:
    """Chunks out of the vector store first; only then the chunk file and the uploaded copies."""
    work = get_settings().work_dir
    chunk_file = work / "chunks" / f"{doc_id}.jsonl"
    uploads = _uploads_of(work / "docs", doc_id) if DOC_ID.fullmatch(doc_id) else []
    if not DOC_ID.fullmatch(doc_id) or not (chunk_file.is_file() or uploads):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Không có tài liệu {doc_id}.")
    try:
        removed = open_vectors().delete_where({"source_type": "document", "doc_id": doc_id})
    except Exception as exc:  # unreachable store: keep the files, so deleting again finishes the job
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Không xoá được chunk của {doc_id} khỏi kho vector ({exc}). Chưa xoá tệp nào.",
        ) from exc
    result = DocumentDeleteResult(
        doc_id=doc_id, chunks_deleted=removed, chunk_file_removed=chunk_file.is_file(), uploads_removed=len(uploads)
    )
    chunk_file.unlink(missing_ok=True)
    for upload in uploads:
        upload.unlink()
        if upload.parent != work / "docs" and not any(upload.parent.iterdir()):
            upload.parent.rmdir()  # the upload's data/work/docs/<job_id>/ folder, now empty
    return result


def _info(path: Path) -> DocumentInfo:
    info = DocumentInfo(doc_id=path.stem, name=path.name)
    try:
        for _, chunk in read_chunks(path):
            if info.chunks == 0:
                info.name = Path(chunk.source_path.replace("\\", "/")).name or path.name
                info.title = chunk.title
                info.data_classification = chunk.data_classification
                info.extractor = chunk.extractor
            info.chunks += 1
    except ChunkFileError:
        pass  # listed with what could be read, so it can still be deleted
    return info


def _uploads_of(docs_dir: Path, doc_id: str) -> list[Path]:
    """Every uploaded copy with these bytes: the same file uploaded twice has one ``doc_id``."""
    if not docs_dir.is_dir():
        return []
    candidates = (p for p in docs_dir.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES)
    return sorted(p for p in candidates if doc_id_for(p) == doc_id)
