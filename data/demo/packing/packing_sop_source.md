# PACK01 - Quy trình đóng gói linh kiện

> **SYNTHETIC DEMO DATA - KHÔNG PHẢI QUY TRÌNH CHÍNH THỨC CỦA DENSO**

- Document ID: `SOP-PACK01-DEMO-001`
- Version: `1.0`
- Process: `PACK01 - Đóng gói linh kiện`
- Purpose: test OCR/RAG/WorkProfile/Expert Review trong MentorMind

## Quy trình chính

1. Xác nhận lot và part.
2. Kiểm tra hộp/khay.
3. Kiểm tra ngoại quan linh kiện.
4. Xác định đúng chiều đặt.
5. Đặt linh kiện vào đúng vị trí.
6. Lặp lại đến khi đủ số lượng.
7. Kiểm tra cuối.
8. Đóng hộp và chuyển bước tiếp theo.

## Exception chính

Nếu phát hiện connector/pin cong hoặc biến dạng:
- dừng đóng gói linh kiện đó;
- tách riêng;
- ghi nhận tình trạng;
- chuyển người phụ trách/QC xác nhận;
- không tự uốn/chỉnh nếu chưa có hướng dẫn được phê duyệt.

## Pass criteria

- đúng part;
- đúng lot;
- đúng số lượng;
- đúng chiều;
- không thấy lỗi ngoại quan rõ ràng;
- nhãn/truy vết đọc được;
- không có exception chưa xử lý.

## Dữ liệu MentorMind cần trích xuất

`process`, `step`, `key_point`, `reason`, `exception`, `action_on_exception`, `pass_criteria`, `provenance`.

## Disclaimer

Tài liệu này chỉ dùng cho demo/test kỹ thuật MentorMind. Khi DENSO cung cấp SOP/Work Instruction chính thức ở vòng sau, tài liệu demo phải được thay bằng nguồn được phê duyệt.
