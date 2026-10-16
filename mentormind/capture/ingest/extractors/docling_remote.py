"""Docling on the team's inference server (``KNOWHOW_DOC_EXTRACTOR=remote``, spec 02 FR-02c).

``POST {KNOWHOW_INFERENCE_URL}/documents/convert`` (multipart ``file``) answers
``{"filename", "num_pages", "document": DoclingDocument.export_to_dict()}``. The document is rebuilt
with ``docling_core`` (a light dependency of docling, ``ingest`` extra) and mapped by the same
:func:`docling_to_raw` as the local extractor, so both give the same ``RawDocument``.

The file leaves this machine: the pipeline runs ``DataGuard`` with the ingest label against this
extractor (``is_cloud`` from the URL) before any file is read (spec 02 FR-01b).
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from mentormind.capture.ingest.extractors.base import ExtractorError
from mentormind.capture.ingest.extractors.docling import SUFFIXES, docling_to_raw
from mentormind.capture.ingest.raw import RawDocument
from mentormind.core.config import Settings
from mentormind.core.providers.errors import ProviderError
from mentormind.core.providers.inference import InferenceClient

CONVERT_PATH = "/documents/convert"


class RemoteDoclingExtractor:
    name = "docling-remote"

    def __init__(self, client: InferenceClient) -> None:
        self._client = client

    @classmethod
    def from_settings(cls, settings: Settings) -> RemoteDoclingExtractor:
        """Raises: ProviderConfigError: ``KNOWHOW_INFERENCE_URL`` is not set."""
        return cls(InferenceClient.from_settings(settings))

    @property
    def is_cloud(self) -> bool:
        return self._client.is_cloud

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in SUFFIXES

    def extract(self, path: Path) -> RawDocument:
        try:
            body = self._client.post_file(CONVERT_PATH, path)
        except ProviderError as exc:  # 422 {"error"} included: the next extractor gets the file
            raise ExtractorError(f"Docling trên máy chủ lỗi với {path.name}: {exc}") from exc
        return docling_to_raw(_docling_document(body.get("document"), path), path)


def _docling_document(payload: Any, path: Path) -> Any:
    """``DoclingDocument`` from its ``export_to_dict()`` form."""
    try:
        module = importlib.import_module("docling_core.types.doc")
    except ImportError as exc:
        raise ExtractorError(
            "Thiếu docling-core để đọc kết quả Docling từ máy chủ: cài extra `ingest` (uv sync --extra ingest)."
        ) from exc
    if not isinstance(payload, dict):
        raise ExtractorError(f"Máy chủ không trả 'document' cho {path.name}.")
    try:
        return module.DoclingDocument.model_validate(payload)
    except ValueError as exc:  # pydantic ValidationError
        raise ExtractorError(f"Kết quả Docling của {path.name} từ máy chủ không hợp lệ: {exc}") from exc
