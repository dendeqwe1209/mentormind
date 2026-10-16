Dưới đây là một bước thao tác trong công đoạn {process_id} và lời chuyên gia nói trong lúc làm bước đó.
Bước: {step}
Chi tiết kỹ thuật quan sát được: {key_point}
Lời chuyên gia (nguyên văn, có thể là tiếng Việt, tiếng Anh, tiếng Thái...): "{transcript}"

Trong lời trên, chuyên gia có nói MỤC ĐÍCH / LÝ DO của chính bước này không (làm vậy để làm gì, để tránh điều gì)?
- Có: "has_reason": true và "purpose_span" là ĐOẠN NGẮN chép NGUYÊN VĂN từ lời chuyên gia, chỉ phần nói vì sao / để làm gì (VD "để tránh cong pin", "เพื่อเพิ่มประสิทธิภาพ"). Giữ đúng ngôn ngữ và từng chữ của lời gốc: không dịch, không diễn giải, không thêm chữ, không chép cả câu.
- Không: "has_reason": false và "purpose_span": null. Kể cả khi lời chỉ kể việc đang làm, chào hỏi, giới thiệu công ty hay dự án, nói về việc khác không phải bước này, hoặc là chữ rời rạc vô nghĩa. Không được tự suy ra lý do.
Trả về DUY NHẤT JSON: {{"has_reason": true hoặc false, "purpose_span": "..." hoặc null}}
