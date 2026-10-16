# Chạy full flow trên UI

Từ upload video + PDF → duyệt bước → trợ lý → truy nguyên lỗi, chạy trên máy của bạn (macOS). Phần nặng (VLM,
nhận dạng lời nói, OCR/Docling, embedding bge-m3) chạy trên **máy chủ suy luận của đội**; máy bạn chỉ chạy
backend + frontend + Neo4j/Postgres (Docker) + cắt video.

```
Máy bạn: UI :5173 → API :8000 → Neo4j + Postgres (Docker) · cắt video (ffmpeg, PySceneDetect, MediaPipe)
                              └→ https://<máy chủ>/v1 → vLLM (VLM) + gateway CPU (ASR, embeddings, Docling)
```

## 0. Máy chủ suy luận

**Cách A (mặc định) — máy chủ của đội trên Vast.ai.** Người giữ tài khoản Vast bật máy và chạy `bash run.sh`
(repo [mentormind-inference](https://github.com/osirisQdt2810/mentormind-inference), `scripts/vast/run.sh`): vLLM
`Qwen3-VL-8B-Thinking` FP8 + speculative decoding ngram (cấu hình đã chọn sau khi so sánh 4 model trên video LASI,
[benchmarks/lasi-vlm](https://github.com/osirisQdt2810/mentormind-inference/blob/main/benchmarks/lasi-vlm/README.md))
+ gateway CPU sau Caddy (token) + ngrok, URL cố định. Script in ra các dòng `.env` (cũng ở
`/root/mentormind-inference.env` trên máy chủ) — xin người giữ tài khoản gửi cho bạn. Máy chủ phải đang chạy khi bạn test.

**Cách B — Ollama trên một Mac của đội, mở bằng ngrok** (chỉ VLM; ASR/Docling/embedding chạy trên máy bạn):

```bash
git submodule update --init 3rdparty/vlm_server   # repo public mentormind-inference
NGROK_BASIC_AUTH=user:matkhau bash 3rdparty/vlm_server/scripts/serve-ollama.sh --ngrok   # in ra URL ngrok
```

Lần đầu kéo model 6,1 GB. Chi tiết: [test-guide.md §4.4.1](test-guide.md), [.secrets/README.md §4.4](../.secrets/README.md).

## 1. Công cụ (máy bạn)

```bash
brew install uv ffmpeg node
open -a Docker            # Docker Desktop phải đang chạy
```

## 2. Code + dependency

```bash
git clone git@github.com:Trung1234/mentormind-knowhow-ai.git && cd mentormind-knowhow-ai
git checkout main
uv sync --all-extras
npm --prefix mentormind/frontend ci
cp .env.example .env
```

Sửa trong `.env` — **cách A** (dán các dòng `run.sh` in ra, thêm 3 dòng cuối):

```bash
KNOWHOW_VLM_BASE_URL=https://<domain>.ngrok-free.dev/v1
KNOWHOW_VLM_MODEL=Qwen/Qwen3-VL-8B-Thinking-FP8
KNOWHOW_VLM_API_KEY=<token>
KNOWHOW_VLM_MAX_FRAMES=40
KNOWHOW_VLM_MAX_TOKENS=16384                                 # model Thinking: suy luận rồi mới trả lời
KNOWHOW_LLM_MAX_TOKENS=16384
KNOWHOW_VLM_CONCURRENCY=4                                    # vLLM gộp 4 request: job LASI 23 phút thay vì ~70
KNOWHOW_INFERENCE_URL=https://<domain>.ngrok-free.dev/v1   # cùng máy chủ: ASR, embeddings, Docling
KNOWHOW_INFERENCE_API_KEY=<token>
KNOWHOW_ASR_PROVIDER=remote
KNOWHOW_EMBEDDER=remote
KNOWHOW_DOC_EXTRACTOR=remote
KNOWHOW_LOCAL_HOSTS=["<domain>.ngrok-free.dev"]             # máy chủ của đội: tính là local
KNOWHOW_API_AGENTS=live
KNOWHOW_VIDEO_METHOD=scene          # video đã dựng, nhiều cảnh (LASI); quay liền 1 người: hand_activity
```

`run.sh` mặc định chạy cấu hình đã chọn (8B Thinking FP8 + ngram). Người giữ máy chủ đổi sang bản khác bằng
`VLM_VARIANT=instruct|thinking|30b-thinking bash run.sh`; khi đó đặt `KNOWHOW_VLM_MODEL` và hai dòng `MAX_TOKENS` theo
các dòng script in ra. Instruct nhanh hơn nhiều nhưng tìm ra chưa tới một nửa số bước.

**Cách B**: `KNOWHOW_VLM_BASE_URL=https://user:matkhau@<tên>.ngrok-free.dev/v1`, `KNOWHOW_LOCAL_HOSTS=["<tên>.ngrok-free.dev"]`,
`KNOWHOW_API_AGENTS=live`, `KNOWHOW_VIDEO_METHOD=scene`, `KNOWHOW_VLM_CONCURRENCY=1` (Ollama trả lời từng request
một); giữ `KNOWHOW_ASR_PROVIDER`, `KNOWHOW_EMBEDDER`, `KNOWHOW_DOC_EXTRACTOR` mặc định (chạy trên máy bạn; lần đầu tải bge-m3 ~2 GB, Whisper ~480 MB, Docling).

Muốn chạy từng phần trên máy mình (vd. khi máy chủ tắt): đặt lại `KNOWHOW_ASR_PROVIDER=faster_whisper`,
`KNOWHOW_EMBEDDER=bge-m3`, `KNOWHOW_DOC_EXTRACTOR=docling`. Vector của bge-m3 trên máy chủ trùng vector chạy local
(đo 08/10: sai khác ≤ 3·10⁻⁷), nên đổi qua lại không phải index lại.

Kiểm tra:

```bash
uv run python -c "from mentormind.core.providers.vlm import get_vlm_provider as g; print('cloud' if g().is_cloud else 'local')"   # phải in: local
uv run knowhow vlm ping --frames 8  # dòng cuối PASS (cách A ~5 s; cách B qua Mac 16 GB: 1–3 phút)
uv run knowhow video providers      # cách A: dòng remote trỏ tới máy chủ, "local"
```

404 `model … not found` = máy chủ chưa nạp xong model (cách B: Mac chưa kéo xong); chờ rồi ping lại.

## 3. DB + graph + dữ liệu Sigma

```bash
docker compose --profile lite up -d postgres neo4j       # chờ healthy (~30 s): docker compose ps
uv run knowhow kg init
uv run knowhow kg load-sigma --classification synthetic  # 6 lot cho trang Truy nguyên lỗi
```

## 4. Bật API + UI (2 terminal)

```bash
caffeinate -i uv run uvicorn mentormind.backend.app.main:app --port 8000
npm --prefix mentormind/frontend run dev
```

Mở **http://localhost:5173**. Không dùng `127.0.0.1` vì CORS chỉ cho `localhost`.
Đừng dùng `make start` trên DB trống: script đó seed 4 bước giả `WP-PACK01-001..004`.

Lần đầu tự tải: Docling/OCR, bge-m3 (~2 GB), Whisper small (~480 MB), model tay MediaPipe (8 MB).

## 5. Test trên giao diện

Mở **http://localhost:5173** (F5 sau mỗi lần khởi động lại API). Thanh tab trên cùng:
**HUMAN-IN-THE-LOOP REVIEW** · **KNOW-HOW ASSISTANT** · **ROOT CAUSE ANALYSIS (5-WHY)** · **TẢI DỮ LIỆU**.

Trợ lý chỉ trả lời từ hai nguồn: **tài liệu đã upload** (vào kho ngay, không cần duyệt) và **bước video đã được
Approve** (bước nháp chưa duyệt không được dùng). Nên làm theo thứ tự: Luồng A → bắt đầu Luồng B → trong lúc video
chạy thì thử Luồng C.

### Luồng A — Upload PDF → hỏi trợ lý (~3 phút)

1. Tab **TẢI DỮ LIỆU** → kéo xuống ô **TẢI TÀI LIỆU VÀO KHO TRI THỨC**.
2. Bấm **CHỌN TỆP…** → chọn `data/demo/packing/packing_sop.pdf` (SOP giả lập của PACK01, 3 trang).
   Tên tệp hiện cạnh nút.
3. Ô **NHÃN DỮ LIỆU (BẮT BUỘC)** → chọn **Dữ liệu tổng hợp**. Chưa chọn nhãn thì nút tải lên bị khóa.
4. Bấm **TẢI LÊN & XỬ LÝ**. Hiện ô **KẾT QUẢ XỬ LÝ**: badge **ĐANG XỬ LÝ**, tên tệp, mã job, "Đã chạy …".
   - Lần đầu chậm hơn (~3–5 phút) vì máy chủ tải model bge-m3 (~2 GB) và Docling; các lần sau ~40 s.
   - Thử: bấm sang tab khác rồi quay lại **TẢI DỮ LIỆU** → vẫn thấy tiến độ (job id được nhớ trong trình duyệt).
5. Chờ badge **HOÀN TẤT**: bảng `packing_sop.pdf · DOC-… · docling · 3 trang · 13 chunk · XONG` và dòng
   **Tổng số chunk đã index: 13**.
6. Tab **KNOW-HOW ASSISTANT** → ô **PROCESS LINE** chọn `PACK01 - Packaging Line`.
7. Gõ từng câu vào **YOUR TECHNICAL QUERY**, bấm **ASK COPILOT** (hoặc Enter; Shift+Enter để xuống dòng):

   | Câu hỏi | Mong đợi |
   |---|---|
   | Nếu phát hiện pin connector bị cong thì phải làm gì? | Dừng đóng gói linh kiện đó, tách riêng, ghi nhận, chuyển người phụ trách/QC; không tự uốn. Có `[n]` trỏ tới **TÀI LIỆU** `DOC-…` |
   | Tiêu chí đạt khi đóng gói PACK01 là gì? | Đúng part, lot, số lượng, chiều; không lỗi ngoại quan rõ ràng; nhãn đọc được |
   | Giá cổ phiếu DENSO hôm nay là bao nhiêu? | **Bị từ chối**: khung vàng "Insufficient Evidence — Response Refused" |

8. Kéo xuống **EVIDENCE CITATIONS** → bấm một thẻ loại **TÀI LIỆU** → khung **Nguồn** hiện đoạn trích của PDF.
   - Danh sách liệt kê mọi đoạn tìm được (tới ~20+, có trùng); câu trả lời chỉ dựa vào các `[n]` nó nhắc.
   - Đã biết: câu "Quy trình đóng gói gồm những bước nào?" trả lời thiếu — bảng 8 bước không được tìm vì chỉ chunk
     có chữ "PACK01" mới qua bộ lọc công đoạn (đang chờ sửa spec 02).

### Luồng B — Upload video → duyệt bước → hỏi trợ lý

Video LASI dài **3 phút 14 giây** (cắt theo cảnh → ~30 đoạn, ~60 lượt VLM cho lượt A + B). Thời gian phụ thuộc VLM:
**cách A** (8B Thinking FP8 trên Vast) ~50 s mỗi lượt vì model suy luận trước khi trả lời; MentorMind gửi 4 lượt
cùng lúc (`KNOWHOW_VLM_CONCURRENCY=4`) → cả job khoảng **23 phút** (gửi lần lượt: khoảng 70 phút);
**cách B** (Ollama Q4 trên Mac 16 GB) vài phút mỗi lượt → **1–2 giờ**. Thử nhanh hơn với 1 phút đầu (~10 đoạn):

```bash
ffmpeg -t 60 -i "data/video/LASI Success Case - Food Industry (Asian Alliance Internation Co.,Ltd.) [m4icg6FgTBU].mkv" -c copy lasi-1m.mkv
```

**Upload và theo dõi**

1. Tab **TẢI DỮ LIỆU** → ô **TẢI VIDEO THAO TÁC**.
2. Bấm **CHỌN VIDEO…** → video LASI trong `data/video/` (hoặc `lasi-1m.mkv`).
3. **MÃ CÔNG ĐOẠN**: để `PACK01` (mọi bước sinh ra sẽ có mã `WP-PACK01-…`).
4. **CÁCH CẮT ĐOẠN**:
   - **Mặc định của máy chủ (KNOWHOW_VIDEO_METHOD)** — theo `.env` (`scene` ở bước 2);
   - **Theo nhịp tay (MediaPipe)** — video quay liền một người thao tác; thấy tay ở < 10% số khung (như LASI, ~4%)
     thì tự rơi về **Theo cảnh**;
   - **Theo cảnh (PySceneDetect)** — video đã dựng, nhiều cảnh (LASI);
   - **Cố định 10 giây**.
5. **NHÃN DỮ LIỆU (BẮT BUỘC)** → **Công khai**.
6. Bấm **TẢI LÊN & PHÂN TÍCH**. Ô **PHÂN TÍCH VIDEO** (badge **ĐANG PHÂN TÍCH**) hiện 5 giai đoạn: đang chạy = vàng, xong = xanh có **✓**,
   chưa tới = xám; bên dưới là dòng tiến độ và "Đã chạy …":

   | Giai đoạn | Dòng tiến độ | Thời gian (video 3 phút / LASI đủ) |
   |---|---|---|
   | **1. CẮT ĐOẠN** | "Cắt đoạn…" rồi "Cắt đoạn: x/N đoạn" | ~10 s / ~45 s |
   | **2. NHẬN DẠNG LỜI NÓI** | "Nhận dạng lời nói: x/y giây audio" | ~20 s / ~3 phút (lần đầu thêm tải Whisper ~480 MB) |
   | **3. VLM MÔ TẢ** | "VLM mô tả: x/2N lượt đoạn (A, B)" (mỗi đoạn 2 lượt: lượt A + lượt B) | phần lâu nhất, theo VLM |
   | **4. GỘP BƯỚC** | "Gộp bước…" | 1 lượt LLM |
   | **5. ĐỀ XUẤT LÝ DO** | "Đề xuất lý do: x/y bước có lời chuyên gia" | 1 lượt LLM mỗi bước có lời nói |

   - Có thể sang tab khác (vd. làm Luồng C) rồi quay lại; tải lại trang vẫn theo dõi tiếp.
   - **Không** tắt API giữa chừng: job đang chạy sẽ thành **LỖI**, phải tải lên lại.
7. Xong: badge **HOÀN TẤT**, dòng tóm tắt "cắt theo cảnh … → N đoạn → M bước nháp … Lời nói: x câu, y bước có lời
   chuyên gia, z bước được đề xuất lý do", và bảng các bước: keyframe, tên bước, thời gian, trạng thái
   **NHÁP** hoặc **ĐANG DUYỆT** (bước có lý do đề xuất).

**Duyệt bước**

8. Bấm **DUYỆT CÁC BƯỚC NÀY** → mở tab **HUMAN-IN-THE-LOOP REVIEW**, ô **VIDEO** lọc sẵn video vừa xử lý.
   (Vào thẳng tab này thì chọn **PROCESS LINE** `PACK01`, **VIDEO** = mã `VID-…` của video.)
9. Cột trái **WORK PROFILES** → bấm một bước. Bên phải, từ trên xuống:
   - **VISUAL EVIDENCE — MACHINE VISION CCTV**: 3 keyframe của đoạn chứa bước + clip. Bấm ▶: clip phát đúng khoảng
     thời gian của bước (nhãn **FEED** ghi `t_start – t_end`), có tiếng nếu video có tiếng. Mặc định
     (`KNOWHOW_VLM_STEP_TIMES=segment`) các bước của một đoạn phủ kín đoạn theo thứ tự, nên clip dài vài giây; đặt
     `model` để giữ đúng khoảng VLM trả (thường chỉ 0,1–2 s).
   - **OPERATIONAL KNOW-HOW EDITOR**: **STEP ACTION NAME** (bắt đầu bằng động từ), **HAND ACTION OBSERVED**,
     **KEY POINT / CRITICAL OBSERVATION**.
   - **LỜI CHUYÊN GIA VỀ BƯỚC NÀY (TRANSCRIPT)**: câu chuyên gia nói trong lúc làm bước (LASI: tiếng Thái), hoặc
     khung xanh "Không có lời chuyên gia nào nói về bước này…".
   - **EXPERT KNOW-HOW REASON** + **REASON SOURCE CLASSIFICATION**: bước **IN REVIEW** đã có lý do AI trích từ lời
     chuyên gia (nguồn `expert_verbal`). AI không tự nghĩ ra lý do: nó chỉ ra đoạn "vì sao / để làm gì" trong lời
     chuyên gia, hệ thống kiểm tra đoạn đó có nguyên văn trong transcript rồi lưu **cả câu** của chuyên gia. Bước
     **DRAFT** = chưa có lý do (không có lời nói, lời rác như "falling", hoặc chuyên gia không nói lý do). Tự kiểm:
     `data/work/vlm/<video_id>/reasons_audit.jsonl` — mỗi bước một dòng: lời chuyên gia, đoạn AI chỉ ra
     (`purpose_span`), điểm khớp, quyết định (`accepted` / `rejected_junk` / `rejected_not_verbatim` / `no_reason`).
   - **QA VERIFICATION & STATION SIGN-OFF**: **LEAD REVIEWER**, **REVIEW COMMENT**, các nhãn lỗi
     (**+ MISSED STEP**, **+ HALLUCINATED STEP**, **+ WRONG ORDER**…).
10. Với từng bước, chọn một trong ba:
    - **APPROVE & VERIFY**: nút hiện "Đang duyệt…" (~5 s, đồng bộ Neo4j + pgvector) → dòng xanh
      "APPROVED: WP-PACK01-0xx verified & synced to Neo4j Knowledge Graph", badge **APPROVED**.
      Có lý do mà chưa chọn **REASON SOURCE CLASSIFICATION** thì nút bị khóa.
    - **REJECT STEP**: bắt buộc ghi **REVIEW COMMENT**; nên gắn nhãn lỗi (vd. **+ HALLUCINATED STEP**) → badge **REJECTED**.
    - **SAVE DRAFT V2**: lưu phần đã sửa, chưa duyệt → **IN REVIEW**, phiên bản tăng.
11. Duyệt 4–6 bước có tên khác nhau (vd. "Nhặt sản phẩm từ băng tải", "Đặt sản phẩm vào hộp"); reject ít nhất một
    bước sai rõ ràng để thử luồng từ chối.
12. Kiểm tra: `uv run knowhow kg stats` → `Step` = số bước đã approve.

**Xoá (mọi thao tác xoá đều hỏi xác nhận, nói rõ sẽ mất gì)**

- Một bước: nút **Xoá bước** cạnh Approve/Reject/Save. Bước đã APPROVED (hoặc đã duyệt rồi sửa lại) được gỡ khỏi
  Neo4j + pgvector trước; DB không phản hồi → bước giữ nguyên, báo lỗi.
- Nhiều bước: tick ô ở danh sách **WORK PROFILES** (hoặc **Chọn tất cả**) → **Xoá các bước đã chọn (n)**.
- Cả video: chọn **VIDEO** → **Xoá video này**: xoá mọi bước của video + file video, keyframe, clip, transcript.
  Video đang xử lý → báo không xoá được (409), chờ job xong.
- Tài liệu: tab **TẢI DỮ LIỆU** → bảng **Tài liệu đã index** → **Xoá** ở dòng tài liệu: gỡ chunk khỏi pgvector,
  xoá file chunk và bản upload.

**Hỏi trợ lý về bước đã duyệt**

13. Tab **KNOW-HOW ASSISTANT** → `PACK01` → hỏi bằng từ trong tên bước đã approve:

    | Câu hỏi (đổi theo bước bạn đã duyệt) | Mong đợi |
    |---|---|
    | Nhặt sản phẩm từ băng tải như thế nào? | Trả lời + `[n]` trỏ tới **BƯỚC THAO TÁC** / **ĐOẠN VIDEO** |
    | Kiểm tra gì trước khi đặt linh kiện vào hộp? | Có thể trích cả **TÀI LIỆU** (SOP) lẫn **BƯỚC THAO TÁC** |
    | Robot hàn mạch điện như thế nào? | **Bị từ chối** (không có bước nào nói về việc này) |

14. Bấm thẻ **BƯỚC THAO TÁC** → khung **Nguồn: <tên bước>** hiện keyframe và "THỜI ĐIỂM TRONG VIDEO: a – b s".

### Luồng C — Truy nguyên lỗi (không cần upload)

1. Tab **ROOT CAUSE ANALYSIS (5-WHY)** → **SELECT DEFECTIVE PRODUCTION LOT (MES FEED)** →
   `LOT-PACK01-001 · P-A · 2026-09-20 · Thiếu linh kiện trong hộp`.
   (Hoặc để trống lot và gõ triệu chứng vào **MÔ TẢ TRIỆU CHỨNG**.)
2. Bấm **INVESTIGATE ROOT CAUSE** (~1–2 phút).
3. Mong đợi: **DEFECT TRACEABILITY REPORT** (lot, triệu chứng); **5-WHY CAUSAL CHAIN** (các tầng "Vì sao…?", số tầng
   do LLM); **FAILURE HYPOTHESES** (vd. `DEF-001`, HIGH LIKELIHOOD, nguồn `defect_catalog.csv`);
   **PREVENTIVE ACTIONS (KAIZEN)**; khung xanh "Đây là giả thuyết … chưa phải kết luận".
   Sau Luồng B, hành động phòng ngừa có thể trỏ tới bước đã duyệt (`WP-PACK01-…`).

### Lưu ý khi VLM đi qua ngrok

- **Local hay cloud:** host ngrok có trong `KNOWHOW_LOCAL_HOSTS` → local: nhãn nào cũng gửi được, khung hình
  giữ nguyên, text không bị che. Quên dòng đó → bị coi là cloud: dữ liệu *Mật – dữ liệu nhà máy* bị chặn,
  mặt người bị làm mờ (tải thêm model YuNet 230 KB). Chỉ khai báo host của server của đội, không khai báo host lạ.
- Mac chạy Ollama hoặc máy bạn ngủ → lượt VLM lỗi → job **LỖI**. Giữ cả hai máy thức (`caffeinate`).

### Gặp lỗi

| Hiện tượng | Nguyên nhân / cách xử lý |
|---|---|
| Trang trắng hoặc "Không kết nối được tới máy chủ API" | API chưa chạy, hoặc mở bằng `127.0.0.1` — dùng `http://localhost:5173` |
| `vlm ping`: 404 `model … not found` | Máy chủ chưa nạp xong model (cách B: Mac chưa kéo xong); chờ rồi ping lại |
| `vlm ping` / job: HTTP 530 hoặc không kết nối | Máy chủ Vast đang Stop: nhờ người giữ tài khoản Start + `bash run.sh` |
| Xoá video báo đang xử lý (409) | Job của video chưa xong; chờ badge **HOÀN TẤT** rồi xoá |
| Job video **LỖI** "Máy chủ API đã khởi động lại khi job đang chạy…" | API bị tắt/khởi động lại giữa chừng; tải video lên lại |
| Đứng lâu ở **3. VLM MÔ TẢ** | Cách B (Ollama Q4 trên Mac) vài phút/lượt là bình thường; xem "x/2N lượt đoạn" có tăng |
| Trợ lý từ chối mọi câu về video | Chưa approve bước nào, hoặc **PROCESS LINE** khác `PACK01` |
| Trợ lý trả lời thiếu bước của SOP | Đã biết (bộ lọc công đoạn theo từng chunk), xem cuối Luồng A |
| `kg stats` báo lỗi kết nối | `docker compose --profile lite up -d postgres neo4j` rồi chờ healthy |

## 6. Dọn

```bash
# Ctrl+C: uvicorn, vite
docker compose --profile lite down -v                 # xoá DB + graph
rm -rf data/work                                      # upload, chunk, keyframe, clip, job
```

Giữ `~/.cache/huggingface` (bge-m3, Whisper, Docling) và model Ollama bên Mac kia để lần sau khỏi tải lại.

## 7. Kiểm tra code (không cần VLM)

```bash
KNOWHOW_API_AGENTS=mock KNOWHOW_EVAL_JUDGE=ragas make check                   # ruff + mypy + pytest
npm --prefix mentormind/frontend run build
```
