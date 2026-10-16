# ❓ Câu Hỏi Cần Chốt — Vinh (Task D1 BE + D2 FE)

> Deadline trả lời: **27/09/2026** để Vinh bắt đầu code đúng hướng

---

## Hỏi anh TRUNG

1. **[Quan trọng nhất]** Team chốt cấu trúc thư mục nào?
   - Phương án A: Giữ `backend/app/` riêng như anh đã tạo template, FastAPI chạy ở đây, import `src/knowhow/` vào bằng PYTHONPATH
   - Phương án B: Gộp API vào `src/knowhow/api/` theo spec 01

2. Khi chuyên gia bấm **Duyệt** (approve) một WorkProfile → BE cần nạp vào Neo4j. Anh sẽ expose `kg/loader.py` theo cách nào để Vinh gọi?
   - Import trực tiếp: `from knowhow.kg.loader import load_profiles`
   - Hay cách khác?
   - **Nếu loader chưa xong:** BE có thể ghi log `"KG skipped"` và coi job là `done` tạm thời không?

3. `GET /health` spec yêu cầu trả `{status, neo4j, milvus}`. Khi chạy `KNOWHOW_DEMO_OFFLINE=1` thì mock luôn là `"ok"` được không?

---

## Hỏi anh PHÚC

4. **[Quan trọng nhất]** `FakeLLM` + `FakeVLM` (task T06-1) xong trước ngày nào? Vinh cần để viết test cho endpoint `/assistant/ask` và `/rca/investigate` mà không gọi API thật.
   - Nếu chưa xong kịp: Vinh tự viết stub tạm rồi swap sau được không?

5. `WorkAssistant` và `RcaAgent` là **async hay sync**? Constructor inject những gì?

   ```python
   # Vinh định gọi thế này, đúng không anh?
   assistant = WorkAssistant(settings=..., retriever=..., llm=...)
   answer = await assistant.ask(AskRequest(...))
   ```

6. Endpoint `POST /videos/{id}/process` cần trigger VLM pipeline background. Hàm Phúc export ra để Vinh gọi tên gì, nằm ở module nào?

   ```python
   background_tasks.add_task(run_vlm_pipeline, video_path, process_id, job_id)
   ```

   Khi xong, hàm đó tự cập nhật bảng `jobs` trong SQLite không, hay Vinh phải tự cập nhật?

---

## Hỏi anh VIỆT HOÀNG

7. Keyframe và clip cắt đoạn sau khi VLM xử lý xong được lưu theo cấu trúc nào?

   ```
   data/work/
     video/{video_id}.mp4
     keyframes/{video_id}/frame_{t}.jpg   ← đúng không?
     clips/{segment_id}.mp4               ← đúng không?
   ```

   Vinh cần để viết `GET /media/{relpath}` và FE play clip đúng đường dẫn.

8. Hàm ingest tài liệu Vinh gọi theo interface nào?

   ```python
   from knowhow.ingest.pipeline import run_ingest

   result = await run_ingest(file_path=..., classification=...)
   ```

   Output trả về `list[DocumentChunk]` hay chỉ ghi ra file JSONL? Sau ingest có cần gọi thêm index vào Milvus không?

---

## Hỏi anh ĐẠT

9. **Kịch bản demo Golden Path** cụ thể là gì? Vinh cần để hardcode câu hỏi gợi ý và pre-fill lot ID trong UI.
   - Ví dụ Vinh đề xuất:
     1. Trang 1: Duyệt profile `WP-PACK01-003` ("Đặt linh kiện A vào ngăn trái")
     2. Trang 2: Hỏi *"Tại sao phải xoay linh kiện 90 độ trước khi đặt?"*
     3. Trang 3: Nhập lot `L-2026-1001-07` bị lỗi `D-03` → xem 5-Why
   - Anh Đạt xác nhận hay điều chỉnh?

10. Tên công đoạn chính thức hiển thị trên UI là gì? Tên chuyên gia giả định (khi agent gợi ý liên hệ) là gì?

---

## Hỏi cả team

11. Ai tạo **dữ liệu mẫu WorkProfile** (`data/samples/review_decisions.json`) để UI Trang 1 có dữ liệu hiển thị?
    - Anh Đạt (task A2)?
    - Anh Phúc (từ FakeVLM output)?
    - Vinh tự tạo hardcode tạm?

12. Confirm port mặc định:
    - Backend FastAPI: `localhost:8000` ✓?
    - Frontend Vite: `localhost:5173` ✓?
    - Khi demo trên tablet thật, `VITE_API_BASE_URL` trỏ vào IP nào?

---

*Cảm ơn các anh! Câu nào chốt được thì reply vào đây hoặc tag Vinh trong chat nhóm nhé.* 🙏
