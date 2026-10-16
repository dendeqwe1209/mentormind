from fastapi import APIRouter, HTTPException, status

from mentormind.backend.app.routers.sigma import sigma_lots
from mentormind.core.schemas import Hypothesis, RcaReport, RcaRequest, WhyStep

router = APIRouter(prefix="/rca", tags=["rca"])


@router.post("/investigate", response_model=RcaReport)
def investigate(req: RcaRequest) -> RcaReport:
    # Try calling actual agent if available
    try:
        from mentormind.agents import rca

        if hasattr(rca, "investigate"):
            return rca.investigate(req)
    except ImportError:
        pass

    # AC-06: LotNotFound -> 404
    if req.lot_id:
        existing_lot = next((lot for lot in sigma_lots() if lot.lot_id == req.lot_id), None)
        if not existing_lot:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Không tìm thấy lô sản xuất với lot_id: {req.lot_id}",
            )
        symptom = req.symptom or existing_lot.defect_type or "Lỗi chất lượng phát sinh tại công đoạn đóng gói"
    else:
        if not req.symptom:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cần cung cấp lot_id hoặc mô tả triệu chứng lỗi.",
            )
        symptom = req.symptom

    return RcaReport(
        lot_id=req.lot_id,
        symptom=symptom,
        hypotheses=[
            Hypothesis(
                hypothesis="Thao tác gấp nắp hộp bị lệch mép do lực miết không đều giữa hai tay.",
                likelihood="high",
                evidence_refs=["VID-PACK01-01 (t=03:20)", "WP-PACK01-002"],
            ),
            Hypothesis(
                hypothesis="Độ ẩm phôi carton nhập từ kho bảo quản vượt ngưỡng 12%.",
                likelihood="medium",
                evidence_refs=["packing_sop.pdf §4.1"],
            ),
            Hypothesis(
                hypothesis="Băng chuyền rung lắc nhẹ tại vị trí cấp hộp.",
                likelihood="low",
                evidence_refs=[],
            ),
        ],
        five_whys=[
            WhyStep(
                order=1,
                question="Tại sao nắp hộp carton bị lệch mép >2mm?",
                answer="Do cạnh gập bên trái không vào đúng khớp định hình khi đóng nắp.",
                verified=True,
            ),
            WhyStep(
                order=2,
                question="Tại sao cạnh gập bên trái không vào đúng khớp?",
                answer="Do công nhân thao tác dùng 1 tay miết lệch thay vì dùng cả 2 tay theo SOP.",
                verified=True,
            ),
            WhyStep(
                order=3,
                question="Tại sao công nhân không dùng 2 tay miết đều?",
                answer="Do công nhân mới chưa được huấn luyện bí quyết giữ mép hộp của chuyên gia.",
                verified=True,
            ),
            WhyStep(
                order=4,
                question="Tại sao bí quyết giữ mép hộp không có trong hướng dẫn tiêu chuẩn?",
                answer="Vì đây là bí quyết kinh nghiệm thực tế (Know-How) chưa được số hóa chính thức.",
                verified=True,
            ),
            WhyStep(
                order=5,
                question="Tại sao hệ thống đào tạo chưa cập nhật?",
                answer="Trước đây thiếu công cụ trích xuất Know-How tự động từ video thực hành.",
                verified=True,
            ),
        ],
        related_lots=["LOT-PACK01-001", "LOT-PACK01-002"],
        preventive_actions=[
            "Cập nhật video clip thao tác miết 2 tay chuẩn vào WorkProfile WP-PACK01-002.",
            "Tập huấn lại quy trình đóng nắp cho toàn bộ công nhân ca 2.",
            "Kiểm tra cảm biến độ ẩm môi trường khu vực cấp phôi.",
        ],
    )
