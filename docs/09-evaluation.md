# 09 — Evaluation (Usefulness Report)

**Owner:** Đạt (golden set, khung đo, báo cáo) · Phúc (chạy Ragas, code) · **Tasks Excel:** S1-9, S2-7, S2-8, S3-2

## 1. Mục tiêu
Sinh tự động số liệu cho Deliverable #4 từ 3 nguồn: chất lượng trích xuất của VLM, chất lượng trả lời của agent, và (sau 12/10) hiệu quả nghiệp vụ.

## 2. Golden set — `data/golden_set/qa.jsonl`
Mỗi dòng:
```json
{"qid": "Q001", "process_id": "PACK01", "type": "how|why|exception|relational|out_of_scope",
 "question": "Vì sao phải đặt linh kiện A nghiêng?",
 "ground_truth": "Để tránh trầy bề mặt khi đóng nắp.",
 "expected_citations": ["WP-PACK01-003"],
 "author": "Đạt", "created_at": "2026-09-30"}
```
`expected_citations` là danh sách `Citation.ref_id` (spec 05) thuộc bất kỳ `source_type` nào: `WP-...` (profile), `DOC-...#...` (chunk tài liệu), `VID-...-Sxxx` (segment), `lot_id`/`defect_code` (sigma). Câu `relational` nên có citation sigma hoặc document.

Phân bố tối thiểu 30 câu: how 10, why 6, exception 5, relational 5, out_of_scope 4 (câu mà trợ lý **phải từ chối**).

Nhãn bước chuẩn cho fps sweep: `data/golden_set/steps/<video_stem>.json` (xem spec 04 mục 6).

## 3. Ba nhóm chỉ số

**A. Trích xuất VLM** (từ `review_events`, spec 08)
- Tỷ lệ profile approve không cần sửa / approve sau khi sửa / reject.
- Phân bố `error_tags` (bỏ sót, bịa, sai thứ tự...).
- Kết quả fps sweep (spec 04): recall, precision, order_accuracy, key_point_recall theo fps.
- `reason_coverage`: % profile `approved` có `reason` khác null, tách theo `data_classification` (`public` / `synthetic`). Ngưỡng MVP: ≥ 60% trên video `synthetic` (video public không có lời chuyên gia nên chỉ báo cáo, không so ngưỡng). Đây là chỉ số chứng minh sản phẩm lưu được "vì sao", không chỉ là SOP.

**B. Chất lượng trả lời** (Ragas trên golden set, bỏ nhóm `out_of_scope`)
| Chỉ số | Ngưỡng MVP |
|---|---|
| faithfulness | ≥ 0.85 |
| answer_relevancy | ≥ 0.80 |
| context_precision | ≥ 0.70 |
| context_recall | ≥ 0.70 |
Thêm hai chỉ số tự tính:
- `refusal_accuracy`: tỷ lệ câu `out_of_scope` bị từ chối đúng + tỷ lệ câu trong phạm vi **không** bị từ chối.
- `citation_hit_rate`: tỷ lệ câu có ít nhất 1 citation nằm trong `expected_citations`.

**C. Nghiệp vụ** (khung cho giai đoạn pilot, ngoài phạm vi 12/10)
- Thời gian thợ mới hoàn thành công đoạn lần đầu, tỷ lệ lỗi D-01..D-06, thời gian điều tra 1 lot lỗi — so với baseline.
- Báo cáo 12/10 chỉ trình bày thiết kế thí nghiệm A/B, không bịa số.

## 4. Functional Requirements
- **FR-01** `knowhow eval ragas --golden data/golden_set/qa.jsonl --out data/work/eval/` chạy Work Assistant trên từng câu, tính nhóm B, xuất `ragas_results.csv` (1 dòng/câu) và `summary.json`.
- **FR-02** Judge LLM cho Ragas lấy từ `get_llm_provider` (config riêng `KNOWHOW_EVAL_LLM_*` được phép khác model của agent). Khuyến nghị: test/CI dùng FakeLLM (AC-02); benchmark cho báo cáo 12/10 dùng judge mạnh (VD GPT-4o-mini hoặc Qwen2.5-72B qua API) vì model ~8B chấm Ragas không ổn định. Được phép vì golden set 12/10 chỉ gồm dữ liệu `public`/`synthetic`; DataGuard vẫn chặn nếu có `factory_confidential`.
- **FR-03** `knowhow eval review-stats` tính nhóm A từ profile store.
- **FR-04** `knowhow eval report` gộp A + B (+ sweep CSV nếu có) thành `data/work/eval/usefulness_report.md`: bảng chỉ số, so ngưỡng (đạt/không đạt), 5 câu trả lời tệ nhất kèm lý do, bảng "Profile cần xem lại" (các `profile_id` trong citation thực tế và `expected_citations` của những câu dưới ngưỡng, kèm `process_id` và số câu liên quan — đầu vào cho vòng lặp sửa profile ở spec 08), phần "Hạn chế" và "Thiết kế thí nghiệm pilot" (nhóm C).
- **FR-05** Mọi lần chạy ghi `run_id`, thời điểm, model, commit hash vào `summary.json` để so sánh giữa các lần.

## 5. Acceptance Criteria
- **AC-01** `qa.jsonl` sai schema (thiếu `ground_truth`) → báo lỗi dòng cụ thể, không chạy.
- **AC-02** Với FakeLLM + golden set fixture 5 câu → `ragas_results.csv` có 4 dòng (1 câu out_of_scope tách riêng), `summary.json` có đủ 4 chỉ số Ragas + 2 chỉ số tự tính.
- **AC-03** `refusal_accuracy` tính đúng trên fixture cố định (kết quả kỳ vọng ghi trong test).
- **AC-04** `review-stats` trên fixture 10 review event ra đúng tỷ lệ và phân bố error_tags.
- **AC-05** `report` sinh markdown có bảng chỉ số với cột "Đạt ngưỡng" = ✅/❌ đúng theo ngưỡng mục 3.
- **AC-06** Fixture có 2 câu dưới ngưỡng cùng trích `WP-PACK01-003` → bảng "Profile cần xem lại" có dòng `WP-PACK01-003` với số câu = 2.
- **AC-07** `review-stats` trên fixture 5 profile approved `synthetic` (3 có `reason`) + 2 `public` (0 có `reason`) → `reason_coverage.synthetic = 0.6` (✅), `reason_coverage.public = 0.0` (không so ngưỡng).

## 5b. Cách hiện thực (chốt khi làm T09-1..4, cần Đạt xem)
- Code ở `evaluation/`, mỗi package một chức năng: `golden/` (`loader`: báo mọi dòng sai kèm số dòng + trường; `distribution`: chỉ cảnh báo thiếu câu), `ragas/` (`judges/`: `base.Judge` lớp nền trừu tượng — template method `score` đếm chỉ số không tính được, lớp con tự đăng ký theo `kind`; `library` = `RagasJudge` + `adapters`, `builtin` = `BuiltinJudge` + `prompts/`, `factory.build_judge`; `runner`, `results`), `review/` (`stats`, `store`), `report/` (`builder`, `sections`), `cli/` (mỗi lệnh 1 module). Model `GoldenQuestion`, `ReviewEvent` ở `core.schemas.evaluation`.
- **Hai judge, chọn bằng `KNOWHOW_EVAL_JUDGE`** (`evaluation/ragas/judges/`, `build_judge`; `summary.json` ghi `judge`): `ragas` (mặc định, `RagasJudge`) = thư viện ragas như dưới; `builtin` (`BuiltinJudge`) = prompt tiếng Việt của dự án, cùng định nghĩa 4 chỉ số, mỗi chỉ số 1 lượt gọi có `json_schema`, `answer_relevancy` = cosine bge-m3, không cần ragas/langchain. Cả hai gọi judge LLM qua `LLMProvider` (DataGuard, che PII, audit); lỗi guard dừng cả lượt chạy. Judge `ragas` chạy song song `KNOWHOW_EVAL_MAX_WORKERS` (mặc định 4; Ollama một luồng: 1), mỗi job tối đa `KNOWHOW_EVAL_TIMEOUT_S` (trống = timeout của judge LLM).
- **Judge `ragas`: 4 chỉ số tính bằng thư viện `ragas` (0.4.3, pin cứng; langchain < 1)**: `ragas.evaluate` với `Faithfulness`, `ResponseRelevancy`, `LLMContextPrecisionWithReference`, `LLMContextRecall`. Judge LLM cắm vào ragas qua `adapters.GuardedRagasLLM` = `LLMProvider` của dự án, nên mọi prompt chấm vẫn qua DataGuard, che PII, audit (client riêng của ragas không được dùng); lỗi guard không bị ragas retry/nuốt mà dừng cả lượt chạy. Embedding (`answer_relevancy`) = embedder của Work Assistant theo `KNOWHOW_EMBEDDER` (bge-m3 tại máy, hoặc cùng bge-m3 trên máy chủ suy luận của đội, spec 02 FR-07d; ở URL cloud câu hỏi bị coi là `factory_confidential` nên bị DataGuard từ chối — khai báo host trong `KNOWHOW_LOCAL_HOSTS`) (`adapters.ProjectEmbeddings`), **dùng chung instance của Work Assistant** (vốn dùng chung với vector store): nạp bản thứ hai cho judge đã làm container `mentormind` (1 GiB) bị OOM-kill khi chạy thật trên LASI 4/10. Tắt telemetry của ragas (`RAGAS_DO_NOT_TRACK=true`). Chỉ số ragas không tính được (judge trả sai định dạng, timeout) → để trống, không bịa; đếm vào `judge_failures`.
- Ngữ cảnh chấm = `snippet` của các citation trong câu trả lời. Câu trong phạm vi mà trợ lý từ chối: không chấm Ragas, tính vào `refusal_accuracy`.
- `refusal_accuracy` = (số câu `out_of_scope` bị từ chối + số câu trong phạm vi được trả lời) / tổng số câu; `summary.json` ghi thêm hai tỷ lệ thành phần. `citation_hit_rate` tính trên câu trong phạm vi (từ chối = trượt).
- Câu `out_of_scope` ghi riêng ra `out_of_scope.csv`. `eval ragas --classification` là nhãn dữ liệu đưa cho judge (mặc định `factory_confidential`, fail closed); judge đọc `KNOWHOW_EVAL_LLM_PROVIDER|BASE_URL|MODEL`, trống thì dùng `KNOWHOW_LLM_*`.
- `review-stats`: "duyệt sau khi sửa" = profile có `version > 1` (spec 08: mỗi lần sửa tăng version); đọc SQLite của spec 08 ở chế độ read-only. `report`: câu "dưới ngưỡng" = có chỉ số dưới ngưỡng, hoặc bị từ chối, hoặc không trích nguồn kỳ vọng.

## 6. Tasks
- [x] T09-1 Schema golden set + validator (AC-01) — Đạt viết nội dung, Phúc viết validator.
- [x] T09-2 Runner Ragas + chỉ số tự tính (AC-02, AC-03).
- [x] T09-3 `review-stats` + `reason_coverage` (AC-04, AC-07).
- [x] T09-4 `report` (AC-05, AC-06).

## Changelog
- v1.0 (23/9): khởi tạo.
- v1.1 (23/9): làm rõ `expected_citations` nhận mọi `ref_id`; khuyến nghị judge LLM; FR-04 thêm bảng "Profile cần xem lại" (AC-06).
- v1.2 (24/9): nhóm A thêm `reason_coverage` (ngưỡng ≥ 60% trên synthetic) và `key_point_recall` từ sweep (AC-07).
- v1.3 (28/9, Phúc): T09-1..T09-4 xong (validator golden set, runner + LLM judge theo định nghĩa Ragas, review-stats + reason_coverage, report); cách hiện thực ở §5b.
- v1.4 (4/10, Phúc): đưa lên `main` cùng spec 06; schema ở `core.schemas.evaluation`, đọc `review_events` từ store SQLite của spec 08.
- v1.5 (4/10, Phúc): chuyển sang thư viện `ragas` (extra `eval`), judge vẫn qua `LLMProvider` + DataGuard; embedding bge-m3 local.
- v1.6 (4/10, Phúc): hai judge chọn bằng `KNOWHOW_EVAL_JUDGE=ragas|builtin` (§5b); `summary.json` + báo cáo ghi judge đã dùng.
- v1.7 (4/10, Phúc): `Judge` thành lớp nền trừu tượng (`judges/base.py`), judge mới = 1 lớp con đặt `kind` + `_score`.
- v1.8 (4/10, Phúc): `KNOWHOW_EVAL_MAX_WORKERS`, `KNOWHOW_EVAL_TIMEOUT_S` cho judge `ragas` (chạy thật trên Ollama: 4 luồng × 180 s → 10/12 chỉ số timeout).
- v1.9 (4/10, Phúc): judge dùng chung bge-m3 của Work Assistant (hết OOM trong container 1 GiB).
- v1.10 (08/10, Phúc): §5b embedding của `answer_relevancy` theo `KNOWHOW_EMBEDDER` (tại máy hoặc máy chủ suy luận, spec 02 v1.5 FR-07d) thay cho "bge-m3 local"; URL cloud từ chối câu hỏi.
