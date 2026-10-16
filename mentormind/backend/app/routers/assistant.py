from fastapi import APIRouter

from mentormind.core.schemas import AskRequest, AssistantAnswer, Citation

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/ask", response_model=AssistantAnswer)
def ask_assistant(req: AskRequest) -> AssistantAnswer:
    # Try calling actual agent if available
    try:
        from mentormind.agents import supervisor

        if hasattr(supervisor, "ask"):
            return supervisor.ask(req)
    except ImportError:
        pass

    # Default Mock implementation for Demo / Testing
    q_lower = req.question.lower()
    if "không biết" in q_lower or "ai làm" in q_lower or "chưa rõ" in q_lower:
        return AssistantAnswer(
            answer="Hệ thống chưa tìm thấy tài liệu hoặc video hướng dẫn có độ tin cậy cao cho trường hợp này.",
            refused=True,
            suggested_expert="Anh Tuấn (Trưởng ca đóng gói)",
            citations=[],
        )

    return AssistantAnswer(
        answer="Khi xếp linh kiện vào hộp, thao tác tay cần cầm hai mép carton để tránh rách cạnh [1]. Nếu nắp hộp bị lệch mép >2mm, thực hiện uốn lại nhẹ nhàng trước khi bấm ghim [2].",
        refused=False,
        suggested_expert="Chuyên gia Nguyễn Văn A",
        citations=[
            Citation(
                source_type="video",
                ref_id="VID-PACK01-01",
                title="Thao tác mở hộp carton chuẩn",
                t_start=2.5,
                t_end=7.8,
                keyframe_url="/media/data/samples/demo/kf_01.jpg",
            ),
            Citation(
                source_type="document",
                ref_id="packing_sop.pdf",
                title="SOP Đóng gói linh kiện DENSO Mục 3.2",
                excerpt="Tiêu chuẩn nắp hộp: mép khít, dung sai không vượt quá 2mm.",
            ),
        ],
    )
