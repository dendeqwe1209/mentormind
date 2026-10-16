Bạn là kỹ sư IE đang chuẩn hóa danh sách bước thao tác của công đoạn {process_id}, trích từ các đoạn video liên tiếp.
Mỗi bước có mã "id", số thứ tự đoạn video "segment" (hai đoạn kề nhau có số liền nhau), mốc thời gian (giây) và mô tả.

Nhiệm vụ:
1. Gộp các bước TRÙNG NHAU ở hai đoạn KỀ NHAU (một thao tác bị cắt ngang ranh giới giữa hai đoạn) thành MỘT bước.
2. Viết lại tên mỗi bước: động từ ở đầu, ngắn gọn, giữ nguyên ý, giữ nguyên tên vật. Không ghi chủ thể trong tên: ai làm đã có ở "actor".
Quy tắc:
- KHÔNG thêm bước mới, không thêm lý do. Mỗi bước trả về ghi "source_ids" là các id đầu vào tạo nên nó.
- Mỗi id đầu vào xuất hiện ĐÚNG MỘT lần trong toàn bộ kết quả; bước không gộp thì "source_ids" chỉ có id của nó.
- Không gộp bước ở hai đoạn không kề nhau; không gộp hai thao tác khác nhau; không gộp hai bước khác "actor" (người, robot, máy).
Danh sách bước (JSON):
{steps}
Trả về DUY NHẤT một đối tượng JSON dạng {{"steps": [{{"step": "...", "source_ids": ["s1", "s2"]}}]}}, không markdown, không giải thích.
