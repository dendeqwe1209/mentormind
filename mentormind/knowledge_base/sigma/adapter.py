"""Validated read-only CSV adapter for the mock Sigma export."""

from __future__ import annotations

import csv
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, Field, ValidationError

log = logging.getLogger(__name__)


class LotRecord(BaseModel):
    lot_id: str
    product_code: str
    process_id: str
    date: date
    shift: Literal["A", "B", "C"]
    operator_id: str
    qty: int = Field(ge=0)


class DefectRecord(BaseModel):
    defect_id: str
    lot_id: str
    process_id: str
    defect_code: str
    description: str
    qty: int = Field(ge=0)
    detected_at: datetime


class DefectCatalogEntry(BaseModel):
    defect_code: str
    symptom_name: str
    known_root_cause_id: str | None = None
    known_root_cause: str | None = None
    prevention_profile_id: str | None = None


class LotNotFound(KeyError):
    pass


class SigmaAdapter(Protocol):
    def get_lot(self, lot_id: str) -> LotRecord: ...
    def list_lots(
        self, process_id: str | None = None, date_from: date | None = None, date_to: date | None = None
    ) -> list[LotRecord]: ...
    def get_defects(self, lot_id: str) -> list[DefectRecord]: ...
    def list_defects(self, defect_code: str | None = None) -> list[DefectRecord]: ...
    def defect_catalog(self) -> list[DefectCatalogEntry]: ...


class CsvSigmaAdapter:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)

    def _rows(self, filename: str, model: type[BaseModel]) -> list:
        with (self.directory / filename).open(newline="", encoding="utf-8") as source:
            rows = []
            for line, raw in enumerate(csv.DictReader(source), 2):
                try:
                    rows.append(model.model_validate({key: value or None for key, value in raw.items()}))
                except ValidationError as exc:
                    log.warning("Skipping invalid %s row %s: %s", filename, line, exc)
            return rows

    def get_lot(self, lot_id: str) -> LotRecord:
        for lot in self.list_lots():
            if lot.lot_id == lot_id:
                return lot
        raise LotNotFound(lot_id)

    def list_lots(
        self, process_id: str | None = None, date_from: date | None = None, date_to: date | None = None
    ) -> list[LotRecord]:
        return [
            row
            for row in self._rows("lots.csv", LotRecord)
            if (process_id is None or row.process_id == process_id)
            and (date_from is None or row.date >= date_from)
            and (date_to is None or row.date <= date_to)
        ]

    def get_defects(self, lot_id: str) -> list[DefectRecord]:
        return [row for row in self.list_defects() if row.lot_id == lot_id]

    def list_defects(self, defect_code: str | None = None) -> list[DefectRecord]:
        return [
            row
            for row in self._rows("defects.csv", DefectRecord)
            if defect_code is None or row.defect_code == defect_code
        ]

    def defect_catalog(self) -> list[DefectCatalogEntry]:
        return self._rows("defect_catalog.csv", DefectCatalogEntry)
