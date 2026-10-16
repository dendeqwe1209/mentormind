## QUY TRÌNH THAO TÁC CHUẨN (SOP) PACK01 - ĐÓNG GÓI LINH KIỆN

SYNTHETIC DEMO DATA - KHÔNG PHẢI QUY TRÌNH CHÍNH THỨC CỦA DENSO

| Mã tài liệu   | SOP-PACK01-DEMO-001                                             | Phiên bản    | 1.0        |
|---------------|-----------------------------------------------------------------|--------------|------------|
| Công đoạn     | Đóng gói linh kiện                                              | Mã công đoạn | PACK01     |
| Loại dữ liệu  | Synthetic / Demo                                                | Ngôn ngữ     | Tiếng Việt |
| Mục đích      | Dùng để test OCR/RAG/WorkProfile/Expert Review trong MentorMind | Ngày tạo     | 2026-09-28 |

## 1. Mục đích

Chuẩn hóa thao tác đóng gói linh kiện trong kịch bản demo MentorMind, đồng thời cung cấp nguồn tài liệu có cấu trúc để hệ thống có thể trích xuất bước thao tác, điểm kiểm soát, lý do, tiêu chí đạt và xử lý bất thường.

## 2. Phạm vi áp dụng

Áp dụng cho kịch bản demo PACK01. Linh kiện được kiểm tra ngoại quan, đặt đúng chiều vào khay/hộp, xác nhận số lượng và trạng thái trước khi đóng hộp.

## 3. Đầu vào / đầu ra

| Loại    | Nội dung                                                                                                        |
|---------|-----------------------------------------------------------------------------------------------------------------|
| Đầu vào | Linh kiện cần đóng gói; hộp/khay đóng gói; nhãn lot; tài liệu hướng dẫn; thông tin lot/part trên hệ thống.      |
| Đầu ra  | Hộp linh kiện đã đóng gói đúng số lượng, đúng chiều, không có lỗi ngoại quan rõ ràng; có thể truy vết theo lot. |

## 4. Dụng cụ / điều kiện

- Khay hoặc hộp đóng gói sạch, không rách/móp.
- Khu vực thao tác đủ ánh sáng.
- Găng tay sạch nếu linh kiện yêu cầu kiểm soát bề mặt.
- Mã lot/part phải đọc được và khớp với lệnh thao tác.
- Không tiếp tục thao tác nếu phát hiện tình trạng bất thường chưa được quy định.

## 5. Quy trình thao tác

|   Bước | Thao tác                                           | Điểm kiểm soát chính                                             | Lý do / ý nghĩa                                                    | Tiêu chí đạt                                   |
|--------|----------------------------------------------------|------------------------------------------------------------------|--------------------------------------------------------------------|------------------------------------------------|
|      1 | Xác nhận lot và part trước khi bắt đầu.            | Đối chiếu lot ID, part code và nhãn hộp.                         | Ngăn đóng nhầm part hoặc nhầm lot.                                 | Thông tin trên hệ thống và nhãn khớp nhau.     |
|      2 | Kiểm tra nhanh tình trạng hộp/khay.                | Hộp sạch, không móp; vị trí chứa linh kiện không bị cản trở.     | Tránh làm hư hỏng linh kiện hoặc tạo lỗi trong quá trình đóng gói. | Khay/hộp đủ điều kiện sử dụng.                 |
|      3 | Lấy từng linh kiện và kiểm tra ngoại quan.         | Quan sát connector/pin, bề mặt, biến dạng, nứt, bẩn hoặc dị vật. | Phát hiện lỗi trước khi linh kiện được đưa vào hộp.                | Không thấy bất thường bằng quan sát trực tiếp. |
|      4 | Xác định đúng chiều đặt linh kiện.                 | Căn theo đặc điểm định hướng hoặc ký hiệu trên linh kiện/khay.   | Tránh va chạm và đảm bảo bố trí đồng nhất.                         | Linh kiện đúng chiều quy định.                 |
|      5 | Đặt linh kiện vào vị trí tương ứng trong hộp/khay. | Đặt nhẹ, không ép; không để linh kiện chồng lên nhau.            | Giảm nguy cơ cong pin, xước hoặc biến dạng.                        | Linh kiện nằm ổn định tại đúng vị trí.         |

|   Bước | Thao tác                                | Điểm kiểm soát chính                              | Lý do / ý nghĩa                                       | Tiêu chí đạt                                           |
|--------|-----------------------------------------|---------------------------------------------------|-------------------------------------------------------|--------------------------------------------------------|
|      6 | Lặp lại đến khi đủ số lượng yêu cầu.    | Đếm số lượng và kiểm tra vị trí trống/bị lặp.     | Ngăn thiếu hoặc thừa linh kiện.                       | Số lượng khớp lệnh đóng gói.                           |
|      7 | Kiểm tra cuối trước khi đóng hộp.       | Kiểm tra chiều, số lượng, ngoại quan và nhãn lot. | Là điểm xác nhận cuối trước khi hoàn tất.             | Không có lỗi quan sát được; thông tin truy vết đầy đủ. |
|      8 | Đóng hộp và chuyển sang bước tiếp theo. | Hộp được đóng đúng cách, nhãn còn đọc được.       | Bảo đảm trạng thái đóng gói ổn định và truy vết được. | Hộp hoàn chỉnh, sẵn sàng chuyển công đoạn.             |

## 6. Xử lý bất thường

| Tình huống                                             | Hành động yêu cầu                                                                                                         | Không được làm                                                                                     |
|--------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------|
| Connector/pin cong, biến dạng hoặc có dấu hiệu hư hỏng | Dừng đóng gói linh kiện đó; tách riêng; đánh dấu tình trạng; chuyển người phụ trách/QC xác nhận theo quy trình hiện hành. | Không tự uốn/chỉnh pin nếu chưa có hướng dẫn được phê duyệt; không tiếp tục đóng gói như hàng đạt. |
| Không xác định được lot/part                           | Tạm dừng thao tác; kiểm tra lại nhãn và thông tin hệ thống; báo người phụ trách nếu vẫn không xác định được.              | Không phỏng đoán part/lot.                                                                         |
| Hộp/khay móp, bẩn hoặc không phù hợp                   | Đổi vật tư đóng gói đạt yêu cầu trước khi tiếp tục.                                                                       | Không dùng hộp/khay lỗi để 'tạm' đóng gói.                                                         |
| Thiếu thông tin hoặc chưa có rule xử lý                | Ghi nhận tình huống và yêu cầu chuyên gia/QC xác nhận trước khi tiếp tục.                                                 | Không để AI hoặc người thao tác tự suy diễn nguyên nhân/hướng xử lý.                               |

## 7. Kiểm tra chất lượng cuối

Một hộp được coi là đạt trong kịch bản demo khi thỏa toàn bộ điều kiện sau:

- Đúng part và đúng lot.
- Đúng số lượng yêu cầu.
- Linh kiện được đặt đúng chiều và đúng vị trí.
- Không có dấu hiệu ngoại quan bất thường rõ ràng.
- Nhãn/truy vết còn đọc được.
- Không tồn tại exception chưa được xử lý/xác nhận.

## 8. Dữ liệu MentorMind cần trích xuất từ SOP này

| Field               | Ví dụ trích xuất                                              |
|---------------------|---------------------------------------------------------------|
| process             | PACK01 - Đóng gói linh kiện                                   |
| step                | Kiểm tra ngoại quan linh kiện trước khi đặt vào hộp           |
| key_point           | Kiểm tra connector/pin, bề mặt và biến dạng                   |
| reason              | Phát hiện lỗi trước khi đóng gói                              |
| exception           | Connector/pin cong hoặc biến dạng                             |
| action_on_exception | Dừng đóng gói, tách riêng, chuyển người phụ trách/QC xác nhận |
| pass_criteria       | Đúng part/lot/số lượng/chiều; không có lỗi quan sát được      |
| provenance          | SOP-PACK01-DEMO-001, section 5-7                              |

## 9. Lưu ý sử dụng

Tài liệu này được tạo riêng cho mục đích demo/test kỹ thuật MentorMind. Nội dung không đại diện cho quy trình vận hành thực tế của DENSO và không được dùng làm hướng dẫn sản xuất thật.

Khi DENSO cung cấp dữ liệu/Work Instruction/SOP chính thức ở vòng sau, tài liệu demo này phải được thay thế bằng nguồn được phê duyệt và giữ đầy đủ provenance/version.

## 10. Revision History

|   Version | Date       | Change                                                 |
|-----------|------------|--------------------------------------------------------|
|       1.0 | 2026-09-28 | Initial synthetic demo SOP for MentorMind PACK01 flow. |