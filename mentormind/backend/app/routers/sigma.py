from fastapi import APIRouter, HTTPException, Query, status

from mentormind.core.config import get_settings
from mentormind.core.schemas import LotRecord
from mentormind.knowledge_base.sigma.adapter import CsvSigmaAdapter, DefectRecord

router = APIRouter(prefix="/sigma", tags=["sigma"])


@router.get("/lots", response_model=list[LotRecord])
def get_lots(
    process_id: str | None = Query(default=None, description="Mã công đoạn"),
) -> list[LotRecord]:
    return sigma_lots(process_id)


def sigma_lots(process_id: str | None = None) -> list[LotRecord]:
    """The Sigma adapter's lots (spec 07) in the API shape: the RCA Agent reads the same source (AC-15)."""
    settings = get_settings()
    if settings.sigma_adapter != "csv":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Chưa có Sigma adapter {settings.sigma_adapter!r} (spec 07).",
        )
    adapter = CsvSigmaAdapter(settings.sigma_csv_dir)
    defects: dict[str, list[DefectRecord]] = {}
    for defect in adapter.list_defects():
        defects.setdefault(defect.lot_id, []).append(defect)
    return [
        LotRecord(
            lot_id=lot.lot_id,
            process_id=lot.process_id,
            part_number=lot.product_code,
            produced_at=lot.date.isoformat(),
            defect_type="; ".join(d.description for d in defects[lot.lot_id]) if lot.lot_id in defects else None,
            status="NG" if lot.lot_id in defects else "OK",
        )
        for lot in adapter.list_lots(process_id)
    ]
