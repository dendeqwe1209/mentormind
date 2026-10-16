# 08 — API, Profile Store & UI

**Owner:** Vinh · **Tasks Excel:** S1-8, S2-4, S3-3 · luồng end-to-end S2-3 (Trung)

## 1. Profile store — `knowledge_base.store.profile_store`
SQLite tại `KNOWHOW_PROFILE_DB`.
```sql
CREATE TABLE profiles (
  profile_id TEXT PRIMARY KEY, process_id TEXT NOT NULL, status TEXT NOT NULL,
  version INTEGER NOT NULL, data_json TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE review_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, profile_id TEXT NOT NULL, action TEXT NOT NULL,
  reviewer TEXT NOT NULL, comment TEXT, error_tags TEXT, created_at TEXT NOT NULL);
CREATE TABLE jobs (
  job_id TEXT PRIMARY KEY, kind TEXT, status TEXT, result_json TEXT, error TEXT,
  created_at TEXT, finished_at TEXT);
```
- Mọi lần ghi validate bằng `validate_against_contract`.
- Sửa nội dung profile → `version += 1`, `status = "in_review"`.
- Xoá profile → xoá luôn các `review_events` của nó.

## 2. REST API (FastAPI) — `backend.app.main:app`
| Method & path | Body / query | Trả về | Ghi chú |
|---|---|---|---|
| `GET /health` | — | `{status, neo4j, postgres}` | |
| `POST /ingest/documents` | multipart `files`, `classification` (bắt buộc) | `{job_id}` | chạy spec 02 run + index, xem dưới bảng |
| `POST /videos` | multipart `file`, `process_id`, `classification` (bắt buộc) | `VideoAsset` | lưu `data/work/video/<video_id>/`, xem dưới bảng |
| `POST /videos/{video_id}/process` | `{method?, fps?}` | `{job_id}` | segment → transcribe → describe → propose-reasons, xem dưới bảng |
| `GET /videos/{video_id}/segments` | — | `list[Segment]` (spec 03 §3) | đọc `data/work/video/<video_id>/segments.json`; trang 1 lấy clip + keyframe từ đây |
| `GET /jobs/{job_id}` | — | `{status, result, error}` | `queued/running/done/failed` |
| `GET /profiles` | `process_id?`, `status?` | `list[WorkProfile + published]` | `published` = bước đang có trong đồ thị (định nghĩa ở "Xoá dữ liệu"), để hộp thoại xoá cảnh báo; không thuộc contract |
| `GET /profiles/{id}` | — | `WorkProfile` + lịch sử review | |
| `PATCH /profiles/{id}` | các trường sửa được | `WorkProfile` | không cho sửa `profile_id`, `generated_by`, `created_at` |
| `POST /profiles/{id}/review` | `{action: approve\|reject, reviewer, comment?, error_tags[]}` | `WorkProfile` | approve → `kg.load_profiles`; reject sau khi đã approved → `kg.unload_profile` |
| `DELETE /profiles/{id}` | — | `ProfileDeleteResult` | xoá một bước, xem "Xoá dữ liệu" dưới bảng |
| `POST /profiles/delete` | `{profile_ids: [...]}` | `ProfileDeleteResult` | xoá nhiều bước |
| `DELETE /videos/{video_id}` | — | `VideoDeleteResult` | xoá mọi bước của video + tệp của video |
| `GET /documents` | — | `list[DocumentInfo]` | tài liệu đã tách chunk, đọc từ `data/work/chunks/*.jsonl` |
| `DELETE /documents/{doc_id}` | — | `DocumentDeleteResult` | chunk trong vector store + file chunk + bản tải lên |
| `POST /assistant/ask` | `AskRequest` | `AssistantAnswer` | spec 06 |
| `POST /rca/investigate` | `RcaRequest` | `RcaReport` | 404 khi `LotNotFound` |
| `GET /sigma/lots` | `process_id?` | `list[LotRecord]` | đọc Sigma adapter (spec 07, `KNOWHOW_SIGMA_ADAPTER`) — cùng nguồn với RCA Agent; cho dropdown UI |
| `GET /media/{relpath}` | — | file | chỉ phục vụ file dưới `data/work/` và `data/samples/`; chặn `..` |

`POST /ingest/documents`:
- `classification` bắt buộc, không có mặc định (spec 02 FR-01b); thiếu hoặc ngoài enum → 422, không lưu tệp, không tạo job.
- Tệp lưu ở `data/work/docs/<job_id>/<tên tệp>`: chỉ giữ phần tên, bỏ mọi thành phần thư mục (`../`, `/`, `\`). Tên rỗng, `.`, `..` hoặc hai tệp trùng tên trong một lần gửi → 422.
- Job chạy `ingest run` trên các tệp đó, ghi chunk vào `data/work/chunks/` như CLI (nên `knowhow ingest index` vẫn thấy), rồi chỉ index các `<doc_id>.jsonl` của lần tải này. Một tệp lỗi không dừng các tệp khác.
- `result` = `{classification, files: [{name, doc_id, extractor, pages, chunks, skipped, error}], chunks_indexed}` (`core.schemas.DocumentIngestResult`). Không tệp nào ra chunk (mọi tệp lỗi hoặc không hỗ trợ) hoặc bước index lỗi → `failed`, `error` nêu lý do, `result` vẫn kèm các tệp đã xét.
- Tài liệu không qua bước duyệt: chunk vào kho tìm kiếm ngay với nhãn đã chọn (spec 02); chỉ WorkProfile cần chuyên gia duyệt (constitution Điều 3).

`POST /videos` và `POST /videos/{video_id}/process`:
- `classification` bắt buộc như tài liệu; đuôi ngoài `.mp4 .mov .mkv .webm .avi .m4v` → 422. `video_id` = `VID-` + sha256[:12] của nội dung (spec 03 §3, trùng id mà `knowhow vlm describe` dùng). Tệp lưu ở `data/work/video/<video_id>/source<đuôi>`, kèm `video.json` = `VideoAsset` của spec 03 §3 (`duration_s`, `fps` đọc bằng OpenCV, `has_audio` bằng ffprobe, `process_id`, `data_classification`) để bước xử lý biết nhãn và công đoạn; tải lại cùng nội dung thì ghi đè `video.json`.
- `process`: `video_id` chưa tải lên (không có `video.json`) → 404. `method` ∈ {`hand_activity`, `scene`, `fixed_window`}, giá trị khác → 422; không gửi (hoặc `null`) → `KNOWHOW_VIDEO_METHOD` (mặc định `hand_activity`). Job chạy `VideoCapturePipeline` của spec 03 (FR-09: cắt theo `method`, thiếu thư viện/model thì rơi xuống cách sau theo spec 03 FR-03; keyframe + clip; transcribe nếu `has_audio`; ghi `segments.json`, `transcript.json`).
- Rồi `DescribePipeline` đủ lượt A, B, C với VLM/LLM cấu hình trong `.env` (DataGuard kiểm trước lời gọi đầu tiên) → profile `draft` vào profile store như `knowhow vlm describe`; mỗi bước mang `transcript_excerpt` của riêng nó (spec 04 §3). Bước có excerpt → `propose-reasons` (LLM, hậu kiểm khớp excerpt); không có transcript thì `reason` để trống, chuyên gia nhập ở trang 1.
- `result.progress = {stage, done, total}`, `stage` ∈ `cut` (cắt + keyframe + clip, đếm theo đoạn), `transcribe` (ASR, theo giây audio), `describe` (lượt gọi VLM của lượt A và B), `merge` (lượt C), `reasons` (theo bước có excerpt). Xong → `result` = `{video_id, process_id, method, method_used, segments, profiles: [profile_id], failed_segments, transcript_lines, steps_with_excerpt, reasons_filled, progress}`. Lỗi → `failed` + message.

Xoá dữ liệu (`DELETE /profiles/{id}`, `POST /profiles/delete`, `DELETE /videos/{video_id}`, `GET`/`DELETE /documents`):
- Bước **đã lên đồ thị** = `status = approved`, hoặc lần review gần nhất là `approve` (bước đã duyệt rồi bị sửa thành `in_review`: graph vẫn giữ bản cũ, AC-01), hoặc `in_review` còn khối `review` mà chưa có review event nào (bước nạp vào store ở trạng thái đã duyệt, không qua API duyệt — `seed_demo`, dữ liệu nhập — rồi `knowhow kg load-profiles` và bị sửa). Bước đó được gỡ bằng `kg.unload_profile` (spec 05 FR-04: xoá `Step` và chunk `work_profile` trong pgvector) **trước**, rồi mới xoá khỏi profile store. Bước khác (`draft`, `rejected`, `in_review` chưa từng duyệt) chỉ xoá khỏi profile store, không mở Neo4j/pgvector — xoá nháp vẫn chạy khi hai dịch vụ này tắt.
- Xoá giữ khoá ghi của profile store từ **trước** khi gỡ tới khi xoá xong (như duyệt giữ khoá khi nạp graph), nên một lần duyệt đang ghi không làm lệnh xoá hết giờ sau khi graph đã gỡ bước; store bị khoá quá `timeout` (5 s) → 503 "Kho profile đang bận", chưa gỡ, chưa xoá gì.
- Video có job xử lý đang `queued`/`running` trong process API (job vẫn còn lưu bước và ghi `data/work/vlm/<video_id>/`) → `DELETE /videos/{video_id}` và mọi lệnh xoá có bước của video đó → 409 kèm lý do tiếng Việt, không xoá gì; job xong hoặc lỗi thì xoá được.
- Gỡ khỏi đồ thị lỗi (Neo4j/pgvector không phản hồi) → bước đó giữ nguyên trong store (store không bao giờ quên một bước mà graph còn phục vụ) và nằm trong `failed`; các bước khác vẫn bị xoá. `ProfileDeleteResult` = `{deleted: [profile_id], unpublished: [profile_id] (các bước đã gỡ khỏi Neo4j + pgvector, nằm trong deleted), failed: [{profile_id, error}]}`.
- `DELETE /profiles/{id}`: id không có → 404; bước đó gỡ lỗi → 503 kèm lý do, không xoá gì.
- `POST /profiles/delete`: danh sách rỗng → 422; có id không tồn tại → 404 nêu các id đó, không xoá gì; id lặp tính một lần. Gỡ lỗi một phần → 200 với `failed`.
- `DELETE /videos/{video_id}`: xoá mọi profile có `evidence.video_id = video_id` như trên, rồi xoá `data/work/video/<video_id>/` (video gốc, `video.json`, `segments.json`, `transcript.json`, `keyframes/`, `clips/`) và `data/work/vlm/<video_id>/`. `video_id` phải là một tên thư mục (chữ, số, `-`, `_`) không bắt đầu bằng `_` (dành cho thư mục của máy chủ, vd. `_incoming` chứa video đang tải lên); không có profile nào lẫn thư mục nào → 404. Có bước gỡ lỗi → giữ nguyên các tệp (bước đó còn dùng keyframe/clip), 200 với `failed`. `VideoDeleteResult` = `ProfileDeleteResult` + `{video_id, files_removed}`.
- `GET /documents`: mỗi `data/work/chunks/<doc_id>.jsonl` (do `POST /ingest/documents` hoặc `knowhow ingest run` ghi, cùng nguồn mà `ingest index` đọc) → `DocumentInfo = {doc_id, name (tên tệp gốc, từ source_path), title, data_classification, extractor, chunks}`, xếp theo tên. Đọc file chunk chứ không đọc vector store vì `VectorStore` không có thao tác liệt kê và file chunk có ở mọi backend.
- `DELETE /documents/{doc_id}`: `doc_id` không đúng dạng `DOC-` + 12 hex, hoặc không có file chunk lẫn bản tải lên → 404. Xoá chunk khỏi vector store trước (`delete_where({"source_type": "document", "doc_id": doc_id})`); store không kết nối được hoặc lỗi → 503, chưa xoá tệp nào (xoá lại sau). Rồi xoá `data/work/chunks/<doc_id>.jsonl` và mọi bản tải lên trong `data/work/docs/` có cùng nội dung (cùng `doc_id`), bỏ thư mục job đã rỗng. `DocumentDeleteResult = {doc_id, chunks_deleted, chunk_file_removed, uploads_removed}`. Node `Document` của graph (chỉ có khi một bước đã duyệt trích tài liệu) không bị đụng.

Job chạy bằng `BackgroundTasks` (MVP, một process). Lỗi trong job → `status=failed`, `error` có message, không làm sập server. Job chết theo process: API khởi động lại khi job còn `queued`/`running` thì job đó không bao giờ xong, nên `GET /jobs/{id}` trả nó `failed` kèm thông báo khởi động lại (job tạo trước lúc process API hiện tại khởi động).

## 3. UI — `ui/streamlit_app.py` (tablet, tiếng Việt)
Cấu hình: `layout="wide"`, cỡ chữ ≥ 16px, nút bấm lớn; UI chỉ gọi REST API, không import trực tiếp module nghiệp vụ.

**Trang 1 — "Duyệt thao tác"**
- Bộ lọc process (PACK01, ASSY02 và mọi mã công đoạn đã có bước trong `GET /profiles`, kể cả mã gõ khi tải video) + trạng thái (mặc định `draft` và `in_review`) + video (các `evidence.video_id` trong danh sách); các bước của một video xếp theo `t_start`.
- Nút **Duyệt các bước này** ở trang 4 mở trang này đúng process + video của video vừa xử lý.
- Mỗi profile: 3 keyframe (ảnh thật từ `evidence.keyframes`, qua `/media`), trình phát clip đúng `t_start–t_end`, có tiếng khi video có audio (clip của đoạn chứa bước, lấy từ `GET /videos/{video_id}/segments`), các trường sửa được (step, hand_action, key_point, exceptions, pass_criteria).
- Ô "Lời chuyên gia (transcript)" hiện `evidence.transcript_excerpt` của riêng bước đó (spec 04 §3: mỗi câu thuộc một bước); chưa có thì ghi rõ và nhắc chuyên gia tự nhập lý do.
- Ô `reason` + chọn `reason_source` (bắt buộc chọn khi có nhập reason).
- Multi-select `error_tags` (bỏ sót / bịa bước / sai thứ tự / sai vật / sai thao tác / khác).
- Nút **Duyệt** / **Từ chối** (từ chối bắt buộc nhập lý do).
- Xoá: nút **Xoá bước** cạnh Duyệt/Từ chối/Lưu; mỗi bước trong danh sách có ô chọn, nút **Xoá các bước đã chọn (n)** trên danh sách (vô hiệu khi n = 0); nút **Xoá video này** cạnh bộ lọc video (vô hiệu khi chưa chọn video). Mọi nút xoá mở hộp thoại xác nhận tiếng Việt nêu cái sẽ mất (số bước — với video: mọi bước của video, kể cả bước bị bộ lọc ẩn —, bước đang có trong đồ thị tri thức theo `published` của `GET /profiles` bị gỡ khỏi đồ thị, tệp video/keyframe/clip); **Huỷ** → không gửi request. Đang xoá: spinner + "Đang xoá…", khoá các nút xoá, Duyệt, Từ chối, Lưu. Xong → thông báo số bước đã xoá; bước không gỡ được khỏi đồ thị hiện lỗi kèm lý do.

**Trang 2 — "Hỏi trợ lý"**
- Chọn công đoạn, ô câu hỏi, câu trả lời với marker [n]; bấm citation → hiện keyframe/clip hoặc đoạn tài liệu. API điền cho UI: mọi citation có `excerpt` (đoạn trích, lấy từ `snippet` của agent); citation `work_profile` có `title` (tên bước), `t_start`/`t_end` và `keyframe_url` (`/media/...`) lấy từ profile.
- Khi `refused` → hiện thông điệp từ chối + tên chuyên gia gợi ý.

**Trang 3 — "Truy nguyên lỗi"**
- Chọn lot (từ `/sigma/lots`) hoặc nhập triệu chứng → bảng giả thuyết (màu theo likelihood), bảng 5-Why (cột "Đã xác minh"), danh sách lô liên quan, bước phòng ngừa, disclaimer. Dropdown có lựa chọn "không chọn lot" để chỉ gửi triệu chứng.

**Trang 4 — "Tải dữ liệu"** (video thao tác + tài liệu)
- Video: chọn tệp video, mã công đoạn (mặc định `PACK01`), cách cắt (Mặc định của máy chủ = `KNOWHOW_VIDEO_METHOD` / Theo nhịp tay / Theo cảnh / Cố định 10 giây) và nhãn dữ liệu (không chọn sẵn) → `POST /videos` → `POST /videos/{id}/process` → tiến độ theo giai đoạn của `result.progress` (Cắt đoạn → Nhận dạng lời nói → VLM mô tả → Gộp bước → Đề xuất lý do). Xong → cách cắt thực dùng, số câu transcript, số bước có lời chuyên gia / có lý do đề xuất. Job id được nhớ trong trình duyệt nên tải lại trang vẫn theo dõi tiếp. Xong → danh sách các bước (profile của video, theo thời gian, kèm keyframe) + nút **Duyệt các bước này** mở trang 1 lọc theo video.
- Tài liệu: chọn một hoặc nhiều tệp `.pdf .docx .xlsx .pptx` và nhãn dữ liệu (Công khai / Dữ liệu tổng hợp / Mật – dữ liệu nhà máy). Không chọn sẵn nhãn: nút **Tải lên & xử lý** bị vô hiệu tới khi có ít nhất một tệp và đã chọn nhãn.
- Gửi `POST /ingest/documents`, rồi hỏi `GET /jobs/{id}` mỗi ~2 giây tới khi `done`/`failed`; hiện trạng thái Đang chờ / Đang xử lý / Hoàn tất / Lỗi, kèm tên tệp và thời gian đã chạy. Như video, job id được nhớ trong trình duyệt: chuyển tab hoặc tải lại trang vẫn thấy tiến độ và kết quả; nút tải lên bị khóa khi job còn chạy.
- Xong → bảng từng tệp (tên, `doc_id`, extractor, số trang, số chunk, bỏ qua/lỗi) và tổng số chunk đã index. Lỗi hiện bằng tiếng Việt, không có stack trace.
- Bảng **Tài liệu đã index** (`GET /documents`: tệp, `doc_id`, nhãn, số chunk; tải lại khi một job tài liệu xong), mỗi dòng có nút **Xoá** → hộp thoại xác nhận tiếng Việt (chunk bị gỡ khỏi kho tìm kiếm, tệp tải lên bị xoá) → `DELETE /documents/{doc_id}`; đang xoá hiện spinner trên dòng đó.

## 4. `make demo` — `scripts/demo.sh`
1. `make up` và chờ healthy → `knowhow kg init` → `knowhow sigma gen-mock` → `knowhow kg load-sigma --classification synthetic`.
2. `knowhow ingest run data/samples/docs --classification synthetic` → `knowhow ingest index`.
3. Với mỗi video trong `data/samples/video/`: segment → describe.
   - `KNOWHOW_DEMO_OFFLINE=1` (mặc định khi không có API key) → dùng `FakeVLM`/`FakeLLM` với fixture, chạy được không cần mạng.
4. Áp kết quả duyệt mẫu `data/samples/review_decisions.json` (mô phỏng chuyên gia) → approve/reject qua API.
5. In 3 câu hỏi mẫu + 1 RCA mẫu ra terminal, rồi in URL UI.

## 5. Functional Requirements
- **FR-01** Profile store như mục 1.
- **FR-02** Toàn bộ endpoint mục 2, có OpenAPI docs tại `/docs`.
- **FR-03** UI 4 trang như mục 3.
- **FR-04** `make demo` như mục 4, tổng thời gian ≤ 10 phút ở chế độ offline.
- **FR-05** CORS chỉ cho origin của Streamlit; không có auth ở MVP (ghi rõ trong README).

## 6. Acceptance Criteria
- **AC-01** `PATCH` một profile approved → `version` tăng, `status` về `in_review`, node trong graph vẫn giữ bản cũ cho tới khi approve lại.
- **AC-02** `review approve` → `GET /profiles/{id}` trả `approved` và `kg stats` tăng 1 Step.
- **AC-03** `review reject` không kèm comment → 422.
- **AC-04** `GET /media/../../etc/passwd` → 400/404, không trả file.
- **AC-05** Job lỗi (VLM raise) → `GET /jobs/{id}` trả `failed` + message; server vẫn phục vụ request khác.
- **AC-06** `/rca/investigate` với lot không tồn tại → 404.
- **AC-07** `KNOWHOW_DEMO_OFFLINE=1 make demo` chạy xong trên máy sạch, exit code 0.
- **AC-08** UI: nhập `reason` mà không chọn `reason_source` → nút Duyệt bị vô hiệu, có thông báo.
- **AC-09** `POST /ingest/documents` với một tệp hỗ trợ và `classification` → job `done`; `result.files` có `doc_id`, `pages`, `chunks` của tệp; các chunk mang đúng nhãn đã chọn và đã được upsert vào vector store (chỉ chunk của lần tải này).
- **AC-10** Tên tệp có thành phần đường dẫn (VD `../../evil.pdf`) → tệp được lưu dưới `data/work/docs/<job_id>/` chỉ theo tên gốc (`evil.pdf`), không ghi ra ngoài thư mục đó.
- **AC-11** Thiếu `classification` hoặc giá trị ngoài enum → 422, không lưu tệp, không tạo job (không còn mặc định `synthetic`).
- **AC-12** Mọi tệp lỗi hoặc không hỗ trợ, hoặc bước index raise → `GET /jobs/{id}` trả `failed` + message; server vẫn phục vụ request khác.
- **AC-13** `POST /videos` → `video_id` = `VID-` + sha256[:12] của nội dung; tệp và `video.json` nằm dưới `data/work/video/<video_id>/`; thiếu `classification` hoặc đuôi không phải video → 422, không lưu tệp.
- **AC-14** `POST /videos/{id}/process` (VLM/LLM giả) → job `done`, `result.profiles` là các profile `draft` của video và `GET /profiles` trả chúng; `GET /videos/{id}/segments` trả các đoạn của lần chạy; `method` khác `fixed_window` → 422; video chưa tải lên → 404; pipeline raise → `failed` + message.
- **AC-15** `GET /sigma/lots` trả đúng các lot của Sigma adapter (CSV mock), và `/rca/investigate` với bất kỳ lot nào trong đó không trả 404 (ở cả chế độ `mock` lẫn `live`).
- **AC-16** `POST /assistant/ask` (live): citation có `excerpt` khi agent có `snippet`; citation `work_profile` của một profile có trong store mang `title` = tên bước, `t_start`/`t_end` của bước và `keyframe_url` dạng `/media/...` khi profile có keyframe.
- **AC-17** Job còn `running` từ trước khi API khởi động lại → `GET /jobs/{id}` trả `failed` + thông báo khởi động lại; job tạo sau khi khởi động vẫn `running`.
- **AC-18** `POST /videos/{id}/process` (bộ cắt, ASR, VLM, LLM giả): `method=hand_activity` khi thiếu MediaPipe → job `done`, `result.method_used="scene"`; `method` ngoài 3 giá trị → 422; video có audio → `transcript_lines` > 0, mỗi bước chỉ trích câu của nó, `steps_with_excerpt` và `reasons_filled` đúng; `progress.stage` đi qua `cut` → `transcribe` → `describe`.
- **AC-19** `DELETE /profiles/{id}` một bước chưa từng duyệt (`draft`, `rejected`) → 200, `deleted = [id]`, `GET /profiles/{id}` → 404, lịch sử review của nó cũng mất; Neo4j/pgvector không được mở (vẫn xoá được khi chúng tắt). id không tồn tại → 404.
- **AC-20** Xoá bước `approved`, hoặc `in_review` sau một lần approve, hoặc bước nạp sẵn ở trạng thái `approved` (không review event) rồi bị sửa → `Step` và chunk `work_profile` biến mất khỏi graph/vector store rồi bước mới bị xoá khỏi store, `unpublished = [id]`; `GET /profiles` trả `published=true` cho đúng các bước đó; Neo4j/pgvector tắt → 503 kèm lý do, bước còn nguyên trong store và graph; profile store đang bị một lệnh ghi khác khoá → 503, bước còn nguyên trong store và graph.
- **AC-21** `POST /profiles/delete` nhiều id (có bước đã duyệt) → xoá hết, bước đã duyệt được gỡ khỏi graph; có id không tồn tại → 404, không xoá gì; danh sách rỗng → 422; Neo4j/pgvector tắt → 200, nháp vẫn bị xoá, bước đã duyệt nằm trong `failed` và còn trong store.
- **AC-22** `DELETE /videos/{video_id}` → mọi bước của video bị xoá (bước đã duyệt được gỡ khỏi graph), `data/work/video/<video_id>/` và `data/work/vlm/<video_id>/` không còn, video khác cùng bước của nó còn nguyên; video không có bước lẫn thư mục, hoặc id không phải tên thư mục → 404; bước đã duyệt không gỡ được → các tệp được giữ, `failed` nêu bước đó; video đang có job xử lý → 409 cho `DELETE /videos/{id}` và cho lệnh xoá bước của video đó, không xoá gì, job xong (kể cả lỗi) thì xoá được; `DELETE /videos/_incoming` → 404, tệp đang tải lên còn nguyên.
- **AC-23** `GET /documents` liệt kê mỗi file chunk (`doc_id`, tên tệp, nhãn, số chunk). `DELETE /documents/{doc_id}` → chunk của tài liệu biến mất khỏi vector store (chunk tài liệu khác còn), file chunk và mọi bản tải lên cùng nội dung bị xoá, `GET /documents` không còn nó; `doc_id` lạ hoặc sai dạng → 404; vector store lỗi → 503, không tệp nào bị xoá.

## 7. Tasks
- [ ] T08-1 Profile store + test.
- [ ] T08-2 API ingest/videos/jobs.
- [ ] T08-3 API profiles + review + nối KG loader (AC-01..03).
- [ ] T08-4 API assistant/rca/sigma/media (AC-04, AC-06).
- [ ] T08-5 Streamlit 3 trang (AC-08).
- [ ] T08-6 `scripts/demo.sh` + fixture offline (AC-07) — phối hợp Trung (S2-3). Khung đã có (preflight + luồng §4); còn thiếu các lệnh của spec 02/03/05/06/07, `data/samples/review_decisions.json` và fixture FakeVLM qua env.
- [x] T08-7 Tải tài liệu: `POST /ingest/documents` chạy thật spec 02 run + index (thay kết quả giả), `classification` bắt buộc, tên tệp chỉ giữ phần tên; trang 4 "Tải tài liệu" (AC-09..AC-12).
- [x] T08-8 Luồng UI đầy đủ: tải video → job xử lý thật (cắt `fixed_window` tạm thay spec 03, keyframe, describe A–C, propose-reasons khi có transcript) → trang 1 có keyframe/clip/transcript và lọc theo video → trợ lý có trích dẫn đủ thông tin, RCA lấy lot từ Sigma adapter; job dở dang khi API khởi động lại → `failed` (AC-13..AC-17).
- [x] T08-9 Nối spec 03 vào luồng UI: `method` cắt, transcribe khi có audio, transcript theo bước, tiến độ theo giai đoạn (AC-18).
- [x] T08-10 Xoá dữ liệu: API xoá một / nhiều bước (bước đã duyệt gỡ khỏi Neo4j + pgvector), xoá cả video (bước + tệp), liệt kê và xoá tài liệu; nút xoá có hộp thoại xác nhận ở trang 1 và trang 4 (AC-19..AC-23).
- [x] T08-11 Sửa sau review phần xoá: bước nạp sẵn đã duyệt rồi bị sửa vẫn được gỡ khỏi đồ thị; `GET /profiles` có `published` cho hộp thoại xoá; khoá store trước khi gỡ (503 khi bận); 409 khi video còn job; `_incoming` không phải video (AC-20, AC-22).

## Changelog
- v1.0 (23/9): khởi tạo.
- v1.1 (27/9): `/health` báo `postgres` thay cho `milvus`.
- v1.2 (27/9): đường dẫn module theo layout mới (bỏ `knowhow.`/`src/knowhow/`, xem spec 01 v1.3).
- v1.3 (29/9, review): cấu hình API (`app_name`, `cors_origins`) nằm trong `core.config.Settings` (spec 01 FR-03); khung `scripts/demo.sh` (T08-6 chưa xong).
- v1.4 (02/10, review): review hoàn tác thất bại khôi phục graph theo bản đang lưu (profile đã approved được nạp lại, không bị gỡ khỏi graph); test AC-01 kiểm graph giữ bản cũ tới khi approve lại; demo nạp Sigma mock bằng `--classification synthetic` (spec 05 FR-05).
- v1.5 (06/10, Phúc): `POST /ingest/documents` chạy thật spec 02 (`ingest run` rồi chỉ index các `<doc_id>.jsonl` của lần tải, qua `capture.ingest.index.index_files`; `ingest index` không đổi) thay cho kết quả giả; `classification` bắt buộc như spec 02 FR-01b (bỏ mặc định `synthetic` vốn có thể dán nhầm nhãn cho dữ liệu nhà máy); tên tệp chỉ giữ phần tên (trước đó `../../x.pdf` hay `/x.pdf` ghi ra ngoài `data/work/docs/`). Thêm trang 4 "Tải tài liệu" (FR-03 thành 4 trang), AC-09..AC-12, task T08-7. Trang 4 làm trong UI React (`mentormind/frontend/`) như 3 trang kia; mục 3 và T08-5 vẫn ghi Streamlit, chưa sửa.
- v1.6 (06/10, Phúc): luồng UI đầy đủ (T08-8). `POST /videos` giữ video theo `video_id` = `VID-`+sha256[:12] nội dung (trùng id của `knowhow vlm describe`) kèm `video.json` (`VideoAsset` spec 03), `classification` bắt buộc; `POST /videos/{id}/process` chạy thật thay kết quả giả (cắt `fixed_window` 10 s của spec 04 FR-05 cho tới khi có spec 03, `DescribePipeline` A–C, lưu nháp vào profile store, `propose-reasons` khi có transcript, `result.progress`); thêm `GET /videos/{id}/segments`. `GET /sigma/lots` đọc Sigma adapter thay 3 lot viết cứng (`LOT-2026-*` không có trong Sigma nên RCA live luôn 404). Citation của `/assistant/ask` có `excerpt`, và `title`/thời điểm/`keyframe_url` cho bước thao tác. Trang 4 thành "Tải dữ liệu" (video + tài liệu); trang 1 có keyframe, clip, transcript, lọc video; trang 3 cho phép không chọn lot. Job dở dang khi API khởi động lại (vd. `make start` lần nữa) → `GET /jobs/{id}` trả `failed` thay vì treo `running`. AC-13..AC-17. Tài liệu không qua bước duyệt (ghi rõ ở §2).
- v1.7 (06/10, Phúc): nối spec 03 vào luồng UI (T08-9): `POST /videos/{id}/process` nhận `method` (`hand_activity` mặc định, `scene`, `fixed_window`; thiếu thư viện thì rơi xuống và `result.method_used` báo cách thực dùng), chạy `VideoCapturePipeline` (cắt + keyframe + clip + transcribe nếu có audio), transcript theo từng bước (spec 04 §3), `propose-reasons` cho bước có excerpt; `result.progress` có `stage` (`cut` → `transcribe` → `describe` → `merge` → `reasons`); trang 4 chọn cách cắt và hiện từng giai đoạn; trang 1 ghi transcript là lời về chính bước đó và đánh dấu lý do AI trích. AC-18.
- v1.8 (06/10, Phúc): `method` bỏ trống → `KNOWHOW_VIDEO_METHOD`; trang 4 có lựa chọn "Mặc định của máy chủ"; thông báo Lưu/Duyệt/Từ chối ở trang 1 không còn bị xóa ngay.
- v1.9 (07/10, Phúc): trang 4 tài liệu nhớ job id như video — chuyển tab/tải lại trang không còn mất tiến độ (trước đây chỉ theo dõi trong lần bấm nút); hiện tên tệp + thời gian đã chạy (lần đầu tải bge-m3/Docling mất vài phút).
- v1.10 (07/10, Phúc): trang 4 video: chip giai đoạn đã xong có dấu ✓; giai đoạn vừa bắt đầu (chưa biết tổng) hiện "<giai đoạn>…" thay vì "0/0" (spec 03 AC-15).
- v1.11 (07/10, Phúc): trình phát ở trang 1 có tiếng (clip giữ audio theo spec 03 FR-06 v1.8, bỏ `muted`); vẫn chỉ phát `t_start–t_end` của bước.
- v1.12 (07/10, Phúc): trang 1 — Approve/Reject/Save hiện spinner + "Đang duyệt…/Đang từ chối…/Đang lưu…" và khóa cả ba nút tới khi API trả về (approve đồng bộ Neo4j + pgvector mất ~5 s, trước đây không có phản hồi gì).
- v1.13 (08/10, Phúc): xoá dữ liệu (T08-10) — trang duyệt bị rối vì không xoá được gì. Thêm `DELETE /profiles/{id}`, `POST /profiles/delete`, `DELETE /videos/{video_id}` (bước + `data/work/video/<id>/` + `data/work/vlm/<id>/`), `GET /documents` (đọc file chunk) và `DELETE /documents/{doc_id}` (chunk trong vector store + file chunk + bản tải lên). Bước đã lên đồ thị được gỡ bằng `kg.unload_profile` trước khi xoá khỏi store; gỡ lỗi thì giữ bước và báo `failed`/503, xoá nháp không cần Neo4j/pgvector. Trang 1: nút Xoá bước, chọn nhiều bước để xoá, Xoá video này; trang 4: bảng tài liệu đã index có nút Xoá; mọi thao tác xoá có hộp thoại xác nhận tiếng Việt. AC-19..AC-23.
- v1.14 (08/10, Phúc, review): xoá dữ liệu — (1) "đã lên đồ thị" gồm cả bước nạp sẵn ở trạng thái `approved` không có review event (`seed_demo`) rồi bị sửa thành `in_review`: trước đây chỉ bị xoá khỏi store, `Step` và chunk còn lại mà không xoá được nữa; (2) `GET /profiles` kèm `published` để hộp thoại xoá ở trang 1 cảnh báo cả bước đã duyệt rồi bị sửa (trước chỉ đếm `status = approved`), hộp thoại xoá video nêu số bước; (3) xoá giữ khoá ghi của SQLite trước khi gỡ khỏi graph (trước đây lệnh duyệt đang ghi làm lệnh xoá hết giờ sau khi graph đã gỡ: 500, store vẫn `approved`), store bận → 503; (4) video còn job xử lý → 409 (trước đây job lưu lại các bước vừa xoá và tạo lại `data/work/vlm/<video_id>/`); (5) `video_id` bắt đầu bằng `_` không phải video (`DELETE /videos/_incoming` xoá mất video đang tải lên). AC-20, AC-22 bổ sung; T08-11.
- v1.15 (08/10, Phúc): trang 1 — bộ lọc process chỉ có PACK01/ASSY02 viết cứng và "Duyệt các bước này" chỉ đặt video, nên video tải lên với mã công đoạn khác (vd. ASSY02 khi lọc đang là PACK01, hay một mã mới) mở ra danh sách trống và không chọn lại được: nút giờ mang theo process của video, bộ lọc liệt kê mọi mã đã có bước.
