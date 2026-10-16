"""Fixed sections of the usefulness report: limits and the pilot design (group C, no numbers)."""

LIMITS = [
    "## Hạn chế",
    "",
    "- Golden set và ground truth video còn ở trạng thái draft, cần chuyên gia duyệt.",
    "- Bốn chỉ số Ragas tính bằng judge ghi ở đầu báo cáo (`ragas` = thư viện ragas 0.4.3, `builtin` = "
    "prompt riêng cùng định nghĩa); judge LLM gọi qua provider của dự án (để đi qua DataGuard); "
    "judge ~8B cho điểm dao động, nên dùng judge mạnh cho số liệu báo cáo.",
    "- `answer_relevancy` dùng embedding bge-m3 chạy local.",
    "- Mỗi cấu hình chạy một lần (`temperature` > 0): chênh lệch nhỏ chưa có ý nghĩa thống kê.",
    "",
]
PILOT = [
    "## Thiết kế thí nghiệm pilot (nhóm C, sau 12/10)",
    "",
    "- **Câu hỏi:** trợ lý có rút ngắn thời gian thợ mới làm đúng công đoạn và giảm lỗi D-01..D-06 "
    "không; RCA có rút ngắn thời gian điều tra một lot lỗi không.",
    "- **Thiết kế A/B:** thợ mới chia ngẫu nhiên hai nhóm cùng công đoạn, cùng ca; nhóm A dùng "
    "trợ lý tại trạm, nhóm B dùng SOP giấy như hiện tại. Kỹ sư QC điều tra các lot lỗi có và "
    "không có RCA.",
    "- **Đo:** thời gian hoàn thành công đoạn lần đầu, tỷ lệ lỗi theo mã trong 2 tuần đầu (Sigma), "
    "thời gian từ phát hiện tới xác định nguyên nhân một lot, so với baseline trước pilot.",
    "- Báo cáo này **không có số nghiệp vụ**: chỉ đo được sau pilot.",
    "",
]
