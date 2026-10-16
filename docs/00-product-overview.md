# 00 — Product Overview (MVP nộp 12/10/2026)

**Owner:** Đạt (PM/BA) · **Reviewer:** Trung

## 1. Bài toán
Đề bài Denso Hackathon: *Accumulate Master Know-How for AI to Learn* — thu thập workflow và cách suy luận của chuyên gia vào knowledge base, kết hợp LLM để tái sử dụng cho tác vụ tương tự, không cần viết tài liệu thủ công.

Công đoạn demo: **xếp linh kiện vào hộp** (kitting/packing), 1 công đoạn duy nhất.

## 2. Người dùng
| Persona | Nhu cầu |
|---|---|
| Chuyên gia (thợ lành nghề) | Chia sẻ bí quyết bằng thao tác + lời nói, không phải viết; được ghi tên |
| Thợ mới | Hỏi "bước này làm thế nào, vì sao" ngay tại trạm |
| QC / Tổ trưởng | Có lot lỗi → truy ra công đoạn, thao tác, nguyên nhân khả dĩ |

## 3. Luồng end-to-end của MVP
```
Video (có/không lời) ─┐
Audio bình luận ──────┼─► Segment + keyframe ─► VLM 3 lượt ─► WorkProfile (draft)
Bản vẽ / SOP (PDF) ───┘                                              │
                                                     Chuyên gia duyệt trên UI
                                                                      │ approved
                         Sigma (mock CSV) ──────► Knowledge Graph (Neo4j) + Vector (Postgres/pgvector)
                                                                      │
                                              Work Assistant / RCA Agent ─► Ragas eval
```

## 4. Phạm vi MoSCoW cho 12/10
**Must**
- M1. Ingest PDF/DOCX/bản vẽ → text có cấu trúc (spec 02).
- M2. Cắt video thành đoạn + keyframe (spec 03).
- M3. VLM sinh WorkProfile nháp hợp lệ theo schema (spec 04).
- M4. UI duyệt WorkProfile: approve / reject / edit (spec 08).
- M5. Nạp profile đã duyệt vào graph + vector, truy vấn hybrid (spec 05).
- M6. Work Assistant trả lời có citation (spec 06).
- M7. Ragas trên golden set 30 câu + báo cáo tự sinh (spec 09).
- M8. `make demo` chạy toàn luồng trên dữ liệu mẫu.

**Should**
- S1. RCA agent dùng Sigma mock (spec 06, 07).
- S2. Transcript lời chuyên gia gắn vào `reason` theo timestamp (spec 03, 04).
- S3. MediaPipe hand-activity để cắt đoạn chính xác hơn (spec 03).
- S4. Self-host Qwen3-VL-8B trên 1 GPU (spec 04 FR-08) — nâng từ C1 vì đã có GPU (A5000 24 GB) và chạy được từ 28/9; architecture §8 yêu cầu chứng minh self-host chạy thật. *(Phúc đề xuất, chờ Đạt xác nhận.)*

**Could**
- C2. Nháp A3/8D xuất PDF.

**Won't (sau 12/10)**
- Tích hợp Sigma thật, camera AI thật, video nhà máy thật, xác thực người dùng.

## 5. Tiêu chí thành công của bản nộp
- Demo end-to-end chạy không lỗi trong ≤ 5 phút.
- Ragas: faithfulness ≥ 0.85, answer relevancy ≥ 0.80 trên golden set.
- Có số liệu fps sweep và log lỗi VLM đưa vào slide.

## 6. Câu hỏi mở (Đạt chốt trước 25/9)
- [ ] BTC yêu cầu nộp gì ngày 12/10: slide, video demo, repo, hay cả ba?
- [ ] Có được mời 1 chuyên gia thật ghi âm nội bộ không?

## Changelog
- v1.0 (23/9): khởi tạo.
- v1.1 (27/9): vector store đổi từ Milvus sang PostgreSQL + pgvector.
- v1.2 (28/9, Phúc): C1 (self-host Qwen3-VL) → S4 do đã có GPU và server chạy được (spec 04 v1.4); chờ Đạt xác nhận.
