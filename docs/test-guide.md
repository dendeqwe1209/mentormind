# Hướng dẫn kiểm thử — Mentor Mind MVP

**Vai trò soạn:** Senior Tester · **Owner:** Trung · **Áp dụng cho:** bản nộp 12/10/2026 ·
**Phiên bản:** 1.2 (07/10/2026). §4, §5, §6, §7.6, §8, §11 đã kiểm trên `main` @ `38f94ec`; §7.1–§7.5 giữ mốc
04/10 (`main` @ `da08a2e`)

Liên quan: [constitution](constitution.md) · [PRD §12](PRD.md) · [BRD §14](BRD.md) · spec 01–09 ·
[setup.md](setup.md) (chạy full flow trên UI) · [10-work-left.md](10-work-left.md) (hạng mục còn thiếu).

## 1. Mục đích và phạm vi

Tài liệu này cho cả đội biết **kiểm gì, kiểm bằng cách nào, khi nào được phép nộp**. Nó không thay thế
Acceptance Criteria trong spec. Nó gom các AC lại thành chiến lược, thêm test case thủ công/E2E cho những
gì pytest không phủ được, và đặt tiêu chí ra cho bản nộp.

- **Trong phạm vi:** luồng PACK01 từ dữ liệu thô đến câu trả lời có citation, RCA trên Sigma mock, báo cáo
  evaluation, bảo vệ dữ liệu, UI tablet, chạy với Qwen3-VL tự host (§4.4).
- **Ngoài phạm vi:** Sigma thật, camera AI, dữ liệu `factory_confidential` thật, SSO, tải/hiệu năng ở quy
  mô production (BRD §8.2).

## 2. Nguyên tắc kiểm thử

1. **Thứ tự nguồn sự thật khi phán đúng/sai:** constitution > contract trong `docs/contracts/` > AC của spec
   > văn xuôi của PRD/BRD/architecture. Hai nguồn mâu thuẫn thì ghi lỗi tài liệu, không tự chọn.
2. **Mỗi AC có ít nhất một test tự động** tên `test_ac_xx_...` (constitution Điều 6). AC chỉ kiểm được bằng
   tay (GPU, UI, máy sạch) phải có test case ở §7 và có kết quả được ghi lại.
3. **Test tự động không gọi mạng thật.** Dùng `FakeVLM`, `FakeLLM`, `RecordingHttp`.
4. **Dữ liệu test chỉ là `public` hoặc `synthetic`.** Không đưa dữ liệu nhà máy vào test, issue hay ảnh chụp.
5. **Không dùng output của model làm ground truth của chính model đó** (PRD §7).
6. **Bốn quy tắc không thương lượng.** Mọi vi phạm là lỗi S1, chặn việc nộp:
   - dữ liệu `factory_confidential` không bao giờ tới provider cloud;
   - `reason` chỉ đến từ lời chuyên gia, VLM không tự điền;
   - chỉ profile `approved` vào knowledge base và câu trả lời;
   - không có citation hợp lệ thì phải từ chối.

## 3. Các tầng kiểm thử

| Tầng | Kiểm gì | Công cụ / lệnh | Khi nào chạy |
|---|---|---|---|
| T0 Tĩnh | Lint, format, kiểu; `mypy --strict` cho `core/schemas` và `core/guard`; JSON Schema hợp lệ | `make check`; CI `ci.yml`, `contract-lint.yml` | Mỗi commit (CI) |
| T1 Unit | Logic từng module với fake provider | `uv run pytest` | Mỗi commit (CI) |
| T2 Contract | Pydantic và `validate_against_contract` khớp `work_profile.schema.json` | pytest (spec 01 AC-04) | Mỗi commit (CI) |
| T3 Integration | Neo4j 5 + Postgres/pgvector thật | `pytest -m integration` (§4.2) | Trước khi merge thay đổi ở `knowledge_base/`; trước khi nộp. **CI không chạy tầng này** |
| T4 API | Endpoint FastAPI | `TestClient` trong `tests/test_api_endpoints.py`, `tests/backend/` | Mỗi commit (CI) |
| T5 E2E | Toàn luồng trên dữ liệu mẫu | `KNOWHOW_DEMO_OFFLINE=1 make demo` | Hằng ngày khi preflight đã xanh (**hiện chưa xanh**, §11); bắt buộc trước khi nộp |
| T6 UI | Màn hình tablet, tiếng Việt, luồng duyệt | Thủ công (§7.4, [setup.md §5](setup.md)). CI chỉ chạy `tsc` + `vite build` | Khi UI thay đổi; trước khi nộp |
| T7 Chất lượng model | Qwen3-VL thật, VLM sweep, Ragas | §4.4; `knowhow vlm sweep`, `knowhow eval ragas` / `report` | Khi đổi prompt, model hoặc profile; trước khi nộp. So với ngưỡng, không pass/fail theo commit |
| T8 Bảo mật | DataGuard, outbound guard, path traversal, `.gitignore` | Tự động trong T1 + một lượt thủ công (§7.3) | Mỗi commit + trước khi nộp |

## 4. Môi trường và lệnh chạy

### 4.1 Cục bộ, không cần docker

```bash
uv sync --all-extras
make check                                  # ruff + mypy + pytest
uv run pytest tests/processing/vlm -k ac_02 # chạy một nhóm
uv run pytest -rs                           # liệt kê test bị skip và lý do
```

Mốc ngày 07/10 trên `main` @ `38f94ec`: `make check` xanh, **605 pass, 23 skip**. 23 skip gồm 4 test OCR mẫu
(`KNOWHOW_RUN_SAMPLE_TESTS=1`), 1 test tải bge-m3 (`KNOWHOW_RUN_SLOW=1`), 17 test pgvector và 1 test Neo4j (§4.2).

Fixture `settings` trong `tests/core/providers/conftest.py` tắt `.env`. Các test khác có thể đọc biến
`KNOWHOW_*` từ `.env` hoặc shell. Nếu một test chỉ fail trên máy bạn, chạy `env | grep KNOWHOW_` trước, rồi xem §4.4.4.

### 4.2 Integration (Neo4j + Postgres)

```bash
uv sync --all-extras    # bắt buộc: thiếu extra thì lỗi thu thập test làm dừng CẢ lượt chạy, kể cả với -m integration
make up                 # spec 01 AC-02: Neo4j và Postgres healthy trong ≤ 120 s
# Chỉ cần hai DB cho tầng này (nhanh hơn, không build mentormind/vlm-server):
#   docker compose --profile lite up -d postgres neo4j

export KNOWHOW_TEST_NEO4J_URI=bolt://localhost:7687
export KNOWHOW_TEST_NEO4J_PASSWORD=change-me
export KNOWHOW_PG_DSN=postgresql://knowhow:change-me@localhost:5432/knowhow
uv run pytest -m integration -rs
make down
```

Mốc ngày 05/10 trên `main` @ `ad3a443`: **19 pass, 0 skip, 515 deselected**. Nếu thấy 17 skip
"PostgreSQL không chạy" thì test pgvector chưa kết nối được (xem dưới).

- Dùng `export`, hoặc đặt biến **trên cùng dòng** với `uv run pytest`. Gán biến trên một dòng riêng mà không
  `export` thì pytest không thấy. Gõ sai tên (`NOWHOW_…`) cũng vậy: test Neo4j sẽ skip.
- Test pgvector chỉ đọc `KNOWHOW_PG_DSN` từ **shell** (`Settings(_env_file=None)`), không đọc `.env`. Mặc định
  là `localhost:5432`.
- Test pgvector **tự skip với mọi lỗi kết nối**, kể cả khi cổng 5432 có một Postgres khác (lỗi
  `role "knowhow" does not exist`). Skip không phải pass: luôn chạy với `-rs` và dán phần tóm tắt skip vào PR.
- Máy đã có Postgres ở 5432 (ví dụ Homebrew `postgresql@16`; kiểm bằng `lsof -nP -iTCP:5432 -sTCP:LISTEN`): đổi
  cổng của container, đừng tắt Postgres kia.

  ```bash
  KNOWHOW_PG_PORT=5433 docker compose --profile lite up -d postgres neo4j
  export KNOWHOW_PG_DSN=postgresql://knowhow:change-me@localhost:5433/knowhow
  ```

  Nếu dùng `.env`, đặt luôn `KNOWHOW_PG_PORT=5433` và `KNOWHOW_PG_DSN=…:5433/knowhow` trong đó. Compose, CLI
  (`ingest`, `kg`, `agent`) và API đọc `.env`, chỉ test pgvector là không đọc.
- Test Neo4j gắn dữ liệu với một token ngẫu nhiên (`IT…`). Dù vậy, vẫn nên dùng một instance Neo4j riêng
  cho test, không dùng chung với DB demo.

### 4.3 API và UI

```bash
uv run uvicorn mentormind.backend.app.main:app --port 8000          # Swagger: http://127.0.0.1:8000/docs
npm --prefix mentormind/frontend ci && npm --prefix mentormind/frontend run dev   # VITE_API_BASE_URL mặc định http://localhost:8000
```

- Mở UI bằng **http://localhost:5173**, không dùng `127.0.0.1`: CORS chỉ cho origin trong `KNOWHOW_CORS_ORIGINS`.
- Sau mỗi lần sửa `.env`, **khởi động lại uvicorn**: settings, profile store và agent được cache trong process.
- Duyệt (`POST /profiles/{id}/review`) luôn cần Neo4j và vector store, kể cả khi `KNOWHOW_API_AGENTS=mock`.
- Xoá bước / video (spec 08 §2 "Xoá dữ liệu"): bước nháp xoá được khi Neo4j và vector store tắt; bước đã duyệt phải
  được gỡ khỏi cả hai trước, nên khi chúng tắt bước đó được giữ lại và API báo lý do. Xoá tài liệu cần vector store.
- `make start` (`./start.sh`) giết mọi tiến trình đang giữ cổng 8000/5173, và khi chưa có `data/work/profiles.sqlite`
  thì seed 4 profile giả `WP-PACK01-001..004`. Dùng được cho demo nhanh; **không dùng** khi kiểm thử với Qwen
  (§4.4), vì profile giả lẫn vào kết quả.
- Từng bước trên UI (upload PDF, upload video, duyệt, hỏi trợ lý, RCA): [setup.md §5](setup.md).

### 4.4 Kiểm thử với Qwen3-VL chạy local (Ollama)

Chỉ dùng dữ liệu `public`/`synthetic`: video LASI là `public`, SOP mẫu là `synthetic`. Thứ tự làm: dựng server
(§4.4.1) → chuyển cấu hình (§4.4.2) → chạy các mức Q0–Q4 (§4.4.3) → ghi kết quả vào §7.6 → quay lại giả lập
trước khi chạy test (§4.4.4).

| Cách chạy | Cấu hình | Ghi chú |
|---|---|---|
| Giả lập (mặc định cho test và demo offline) | `KNOWHOW_VLM_PROVIDER=fake`, `KNOWHOW_LLM_PROVIDER=fake` | Không mạng, kết quả tất định |
| Tự host Qwen3-VL bằng Ollama (macOS hoặc Linux) | Server theo §4.4.1, cấu hình theo §4.4.2 | Mặc định của code: `local_openai` → `http://127.0.0.1:11434/v1`, model `qwen3-vl:8b` |
| Ollama của đội ở máy khác qua ngrok | [setup.md](setup.md) §0, §2 (`KNOWHOW_LOCAL_HOSTS`) | Vẫn là server của đội, nên được khai báo là local |
| Cloud (OpenRouter, SiliconFlow, Qwen API) | Key trong `.env` (`uv run knowhow vlm providers`) | Không bao giờ dùng với dữ liệu mật |

Giá trị mặc định trong code (`mentormind/core/config/settings.py`) đã là `KNOWHOW_VLM_PROVIDER=local_openai`,
tức Qwen3-VL qua Ollama. Giả lập chỉ xuất hiện ở ba chỗ: test tự động (`FakeVLM`/`FakeLLM`), `make demo` khi shell
không có key cloud (`scripts/demo.sh` tự đặt `fake`), và router API (`KNOWHOW_API_AGENTS=mock`). Vì vậy
"chuyển source sang Qwen" nghĩa là gỡ ba chỗ đó, không phải đổi code.

**Qwen được gọi ở đâu.** Chỉ những luồng dưới đây gọi Qwen. Tài liệu, transcript và embedding chạy bằng model
local khác, nên không cần Qwen để kiểm chúng.

| Luồng | Lệnh / endpoint | Lượt gọi Qwen | Thành phần local khác |
|---|---|---|---|
| Khói | `knowhow vlm ping` | VLM: 1 | — |
| Cắt video, transcript | `knowhow video probe/segment/transcribe` | Không gọi | ffprobe/ffmpeg, OpenCV, MediaPipe, PySceneDetect, faster-whisper |
| Mô tả bước | `knowhow vlm describe` | VLM: lượt A 1/đoạn, lượt B thêm 1/đoạn (`--no-consistency` bỏ lượt B). LLM: lượt C 1 lần (`--no-merge` bỏ lượt C) | — |
| Đề xuất lý do | `knowhow vlm propose-reasons` | LLM: 1 cho mỗi bước có `transcript_excerpt` | rapidfuzz hậu kiểm trích dẫn (≥ 85) |
| Video qua API/UI | `POST /videos/{id}/process` (tab **TẢI DỮ LIỆU**) | = cắt + transcript + describe (A, B, C) + đề xuất lý do | như hai dòng trên |
| Tài liệu | `knowhow ingest run/index`, `POST /ingest/documents` | Không gọi | Docling, bge-m3 |
| Duyệt | `POST /profiles/{id}/review` | Không gọi | Neo4j, vector store |
| Trợ lý | `knowhow agent ask`, `POST /assistant/ask` (`live`) | LLM: 1 lượt router chọn template graph (bỏ qua nếu LLM là cloud) + 1 lượt trả lời (+1 hỏi lại nếu marker `[n]` sai). Câu bị chặn ở cổng RRF/cosine không có lượt trả lời | bge-m3, Neo4j, pgvector |
| RCA | `knowhow agent rca`, `POST /rca/investigate` (`live`) | LLM: 1 (+1 hỏi lại khi JSON hỏng) | Neo4j, pgvector, Sigma CSV |
| Đánh giá | `knowhow eval ragas` | LLM của trợ lý + judge (`KNOWHOW_EVAL_LLM_*`, rỗng = cùng Qwen) | bge-m3 |

Ollama mặc định xử lý một request một lúc. Khi job video đang ở giai đoạn **3. VLM MÔ TẢ**, câu hỏi trợ lý hoặc RCA
gửi cùng lúc sẽ xếp hàng sau từng lượt VLM (mỗi lượt vài phút, §4.4.1).

#### 4.4.1 Chuẩn bị máy và chạy Qwen3-VL bằng Ollama

**Công cụ** (macOS; Linux dùng trình quản lý gói tương ứng):

```bash
brew install uv ffmpeg node          # ffmpeg BẮT BUỘC cho mọi lệnh video (cắt clip, tách audio)
ffmpeg -version | head -1 && ffprobe -version | head -1
uv sync --all-extras
npm --prefix mentormind/frontend ci  # chỉ cần cho Q3
open -a Docker                       # chỉ cần cho Q2–Q4 (Neo4j + Postgres)
```

Thiếu `ffmpeg`: `video segment` và `vlm describe --video` dừng với `Lỗi: Cần ffmpeg trong PATH để cắt clip`. Thiếu
`ffprobe` còn nguy hiểm hơn: video có tiếng bị đọc bằng OpenCV và **bị coi là video câm** (chỉ có một dòng log
cảnh báo). Khi đó transcript rỗng, không bước nào được đề xuất lý do, và kết quả trông giống hệt case C2 "video câm".

Dung lượng tải lần đầu: Qwen3-VL Q4 6,1 GB, bge-m3 ~2,2 GB, Whisper small ~480 MB, model Docling, model tay
MediaPipe 8 MB. Máy 16 GB: Qwen nằm trên GPU khoảng 7,7 GB (context 16k). Nếu chạy cùng lúc API (bge-m3), Neo4j
và Postgres thì máy sát giới hạn RAM: đóng ứng dụng khác và kiểm `ollama ps` sau mỗi lượt.

**Đường A — script của submodule `mentormind-inference` (trước: vlm-engine).** Dùng khi cần số đo cho báo cáo: đặt sẵn context và số token tối
thiểu mỗi ảnh (`--image-min-tokens`, mặc định 512; Ollama tự ép 1024 token cho mỗi ảnh Qwen-VL).

```bash
git submodule update --init 3rdparty/vlm_server   # repo public: https://github.com/osirisQdt2810/mentormind-inference
make vlm-server         # bash 3rdparty/vlm_server/scripts/serve-ollama.sh, đọc VLM_SERVER_* trong .env
make vlm-server-smoke   # = uv run knowhow vlm ping --frames 8
make vlm-server-stop
```

Script tải Ollama 0.35.1, đặt context (macOS 49152, Linux 98304) và có `--ngrok` để mở cho máy khác. Hướng dẫn:
`3rdparty/vlm_server/scripts/README.md`. **Chưa chạy thử khi cập nhật guide**: thư mục submodule vẫn trống trên máy
kiểm (07/10).

**Đường B — Ollama thuần, không cần submodule.** Đã chạy thử ngày 05/10 và 07/10 (Ollama 0.35.1, Mac M4 16 GB).

```bash
# 1. Cài và bật Ollama (macOS: app Ollama hoặc `brew install ollama`; Linux: script cài của ollama.com)
ollama serve                                  # bỏ qua nếu app Ollama đã chạy
curl -s http://127.0.0.1:11434/api/version    # {"version":"0.35.1"}

# 2. Tải model (~6,1 GB, Q4_K_M)
ollama pull qwen3-vl:8b

# 3. Tạo bản có context lớn. Ollama mặc định chỉ 4096 token, không đủ cho ảnh.
MF=$(mktemp) && printf 'FROM qwen3-vl:8b\nPARAMETER num_ctx 16384\n' > "$MF" \
  && ollama create qwen3-vl-8b-16k -f "$MF"
ollama show qwen3-vl-8b-16k | grep num_ctx    # num_ctx  16384
```

**Chọn context và số khung.** `num_ctx` phải chứa cả token vào (ảnh + prompt) lẫn token ra (phần "nghĩ" + JSON).
Ollama ép khoảng 1024 token mỗi ảnh (8 khung = 8409 token vào). Phần "nghĩ" của lượt A thật dài hơn nhiều so với
ping: đo ngày 07/10, 7 khung LASI cho ra 6348 token, so với 364 token của ping. Tổng cộng ≈ 14,3k, tức đã dùng 87%
của 16k. Hệ quả:

- `vlm ping --frames N` **không đọc** `KNOWHOW_VLM_MAX_FRAMES`; `vlm describe`, `vlm sweep` và job video của API thì có.
  Ping PASS chưa chứng minh được describe chạy vừa context.
- Đường B với model 16k: đặt `KNOWHOW_VLM_MAX_FRAMES=8` (trần). Nếu thấy `failed_segments.json` hoặc JSON bị cắt cụt,
  giảm xuống 6.
- Sampler bỏ khung trùng **trước** khi áp trần: đoạn LASI 60–70 s ở 4 fps chỉ còn 7 khung. Vì vậy, để `40` như
  `.env.example` thì đoạn tĩnh vẫn chạy được, nhưng đoạn nhiều chuyển động giữ tới 40 khung (~41k token vào), vượt
  context, và cả lệnh dừng với HTTP 400. Lỗi chỉ hiện ở một số video, nên dễ bị tưởng là lỗi ngẫu nhiên.
- Context 32k trên máy 16 GB đã tràn sang CPU (04/10). Muốn nhiều khung hơn thì dùng đường A (512 token/ảnh,
  40 khung ≈ 22k token).

Sau mỗi lần gọi, kiểm model có nằm hết trên GPU không: `ollama ps` (cột PROCESSOR phải là `100% GPU`) hoặc
`curl -s http://127.0.0.1:11434/api/ps` (`size_vram` bằng `size`).

**Thời gian để lên kế hoạch** (đường B, M4 16 GB): một lượt VLM của lượt A khoảng **8–9 phút**, một lượt LLM văn bản
từ khoảng 20 giây đến 2 phút (đo được 24 s và 116 s). Một đoạn video tốn 2 lượt VLM (A + B), hoặc 1 lượt với `--no-consistency`; cộng thêm 1 lượt sửa
khi câu trả lời là JSON lỗi hoặc tiếng Anh (spec 04 AC-20). Theo
[setup.md](setup.md), 3 phút LASI cắt theo cảnh ra khoảng 5–8 đoạn, tức theo ước tính **1,5–2,5 giờ** với A + B.
Vì vậy, để kiểm luồng, dùng clip 30 giây và `--no-consistency`.

**Mốc đo tham chiếu** (Mac M4 16 GB, Ollama 0.35.1):

| Ngày | Cấu hình | Kết quả |
|---|---|---|
| 04/10 | Script đường A cũ, 1024 token/ảnh, context 16k, `vlm ping`, 8 khung | PASS, khoảng 87 s, 100% GPU. Context 32k tràn 29% sang CPU |
| 05/10 | Đường B, `qwen3-vl-8b-16k`, `vlm ping`, 8 khung | PASS, 111 s, 8409 token vào / 255 ra, 100% GPU |
| 05/10 | Đường B, `qwen3-vl:8b` mặc định (context 4096), `vlm ping`, 8 khung | Lỗi HTTP 400 `exceed_context_size_error`: 8409 > 4096 |
| 05/10 | `KNOWHOW_VLM_BASE_URL` trỏ tới cổng không có server | `Lỗi: … Connection refused` sau khoảng 8 s, không treo (RES-05) |
| 07/10 | Đường B, `qwen3-vl-8b-16k`, `vlm ping`, 8 khung, `main` @ `38f94ec` | PASS, 116,5 s, 8409 vào / 364 ra, 100% GPU |
| 07/10 | Đường B, `qwen3-vl-8b-16k`, **lượt A thật** trên 1 đoạn LASI 10 s (giây 60–70), `max_frames=8` → còn 7 khung sau khi bỏ khung trùng | 518 s, 7941 vào / 6348 ra, 2 bước tiếng Việt ("Nhặt sản phẩm từ băng tải", "Đặt sản phẩm vào hộp"), `actor=human`, 0 đoạn lỗi, 100% GPU. Chạy bằng script gọi `describe_segments`, vì máy kiểm thiếu ffmpeg nên không chạy được `vlm describe` |
| 07/10 | Đường B, LLM = cùng Qwen 16k, `propose_reasons` trên 2 profile tổng hợp | Câu có lý do: `reason` = "nếu không sẽ trầy mặt khi đóng nắp hộp" (nguyên văn), `expert_verbal`, `in_review`, 116 s. Câu không có lý do: `reason = null`, giữ `draft`, 24 s |

#### 4.4.2 Chuyển source code sang Qwen

`.env.example` đã điền sẵn giá trị cho Ollama, nhưng **giả định đường A** (`qwen3-vl:8b`, 40 khung). Settings đọc
cả `.env` lẫn biến shell; **biến shell thắng `.env`**.

```bash
cp .env.example .env    # nếu chưa có .env
```

Với đường B, sửa các dòng sau trong `.env`. Đừng viết chú thích cùng dòng với một giá trị rỗng: dotenv sẽ đọc
chú thích thành giá trị.

```bash
KNOWHOW_VLM_PROVIDER=local_openai
KNOWHOW_VLM_BASE_URL=
KNOWHOW_VLM_MODEL=qwen3-vl-8b-16k
KNOWHOW_VLM_MAX_FRAMES=8
KNOWHOW_LLM_PROVIDER=
KNOWHOW_LOCAL_HOSTS=[]
KNOWHOW_VIDEO_METHOD=scene
```

Kiểm tra (đây cũng là mức Q0 ở §4.4.3):

```bash
uv run knowhow vlm providers        # dòng local_openai có dấu *
uv run python -c "from mentormind.core.providers.vlm import get_vlm_provider as v; from mentormind.core.providers.llm import get_llm_provider as l; [print(p.name, p.model, 'cloud' if p.is_cloud else 'local') for p in (v(), l())]"
uv run knowhow vlm ping --frames 8  # dòng cuối: PASS
```

Lệnh Python in hai dòng `local_openai qwen3-vl-8b-16k local`: VLM và LLM cùng là Qwen local.

Các công tắc, từ giả lập sang Qwen:

| Biến | Giả lập | Qwen3-VL qua Ollama | Tác dụng |
|---|---|---|---|
| `KNOWHOW_VLM_PROVIDER` | `fake` | `local_openai` (mặc định của code) | Chọn provider cho VLM |
| `KNOWHOW_VLM_BASE_URL` | — | rỗng = `http://127.0.0.1:11434/v1` | Trong container `mentormind`: `http://vlm-server:11434/v1` (compose tự đặt). Máy khác qua ngrok: `https://user:pass@<tên>.ngrok-free.dev/v1` |
| `KNOWHOW_VLM_MODEL` | — | `qwen3-vl:8b` (đường A) hoặc `qwen3-vl-8b-16k` (đường B) | Tên model trong Ollama |
| `KNOWHOW_VLM_MAX_FRAMES` | — | 40 (đường A), 8 (đường B) | Số khung tối đa mỗi đoạn (describe, sweep, API). Mặc định của code là 48 |
| `KNOWHOW_VLM_TIMEOUT_S`, `KNOWHOW_LLM_TIMEOUT_S` | — | 1800 (`.env.example`) | Mặc định của code là 900 s. Một lượt A đo được 518 s, nên đừng hạ thấp hơn |
| `KNOWHOW_LLM_PROVIDER` | `fake` | rỗng | Rỗng = LLM dùng chung provider, server, model với VLM: Qwen3-VL trả lời cả văn bản |
| `KNOWHOW_LOCAL_HOSTS` | — | `[]`; với ngrok: `["<tên>.ngrok-free.dev"]` | Host public nhưng là server của đội thì tính là local (spec 04 AC-23). Chỉ đúng tên, không gồm subdomain |
| `KNOWHOW_VIDEO_METHOD` | — | `scene` cho LASI; `hand_activity` cho video quay liền một người | Cách cắt khi UI/CLI không chọn |
| `KNOWHOW_ASR_*` | — | `faster_whisper`, `small`, `cpu`, `int8`; `KNOWHOW_ASR_LANGUAGE` rỗng = tự nhận | Không phải Qwen; `faster_whisper` chạy tại máy, `remote` chạy trên máy chủ suy luận |
| `KNOWHOW_INFERENCE_URL` | — | rỗng (mọi thứ tại máy) | Máy chủ suy luận của đội cho `KNOWHOW_ASR_PROVIDER` / `KNOWHOW_DOC_EXTRACTOR` / `KNOWHOW_EMBEDDER` = `remote` (Whisper, Docling, bge-m3). Local/cloud theo URL + `KNOWHOW_LOCAL_HOSTS` như VLM |
| `KNOWHOW_API_AGENTS` | `mock` (mặc định) | `live` | `/assistant/ask`, `/rca/investigate` gọi agent thật. Cần Neo4j, vector store và LLM; thiếu thì 503, lot lạ thì 404 |
| `KNOWHOW_EVAL_JUDGE` | `ragas` (mặc định của code) | `builtin` | `.env.example` đặt `builtin` cho demo Ollama. Judge của báo cáo nộp vẫn phải là model mạnh (EVAL-02) |

Một lần chạy lẻ không cần sửa `.env`: `--provider` có ở `vlm ping`, `vlm describe`, `vlm sweep`; `--llm-provider`
có ở `vlm describe` và `vlm propose-reasons`. Hoặc đặt biến ngay trước lệnh (`KNOWHOW_VLM_MODEL=… uv run knowhow vlm ping`).
CLI đọc lại `.env` mỗi lần chạy. API thì phải khởi động lại (§4.3).

Về dữ liệu: `local_openai` trỏ tới `localhost`, IP LAN/Tailscale, tên máy LAN hoặc host có trong
`KNOWHOW_LOCAL_HOSTS` thì được coi là local, nên nhận dữ liệu mật. URL ngrok hoặc host public khác bị coi là cloud:
DataGuard chặn dữ liệu mật, khung hình bị làm mờ mặt, text bị che PII, và `eval ragas` cần `--classification public`
(SEC-02). Lệnh Python ở trên cho biết chắc chắn VLM/LLM đang là `local` hay `cloud`.

#### 4.4.3 Các mức kiểm thử với Qwen (Q0–Q4)

Mỗi mức dùng kết quả của mức trước. Ghi kết quả vào §7.6, kèm commit hash, model và `KNOWHOW_VLM_MAX_FRAMES`.
Trước lượt chạy chính thức, nên bắt đầu từ thư mục làm việc sạch. Đổi tên thay vì xóa:
`mv data/work data/work.bak-$(date +%m%d)`.

**Q0 — Khói (≈ 3 phút, không cần Docker).** Ba lệnh kiểm tra ở cuối §4.4.2 → QWEN-01. Thêm QWEN-02, QWEN-03 khi
đổi máy hoặc đổi model.

**Q1 — Video → hồ sơ nháp bằng CLI (không cần Docker; cần ffmpeg).** Dùng clip 30 s của LASI, đặt trong
`data/work/` (đã gitignore) để `git status` vẫn sạch (SEC-06).

```bash
LASI="data/video/LASI Success Case - Food Industry (Asian Alliance Internation Co.,Ltd.) [m4icg6FgTBU].mkv"
mkdir -p data/work && ffmpeg -ss 60 -t 30 -i "$LASI" -c copy data/work/lasi-30s.mkv
V=data/work/lasi-30s.mkv

uv run knowhow video probe "$V" --classification public       # "has_audio": true  (LASI có tiếng Thái)
uv run knowhow video segment "$V" --classification public     # dòng đầu: VID-… | <thời lượng>s | cách cắt scene | N đoạn, …
uv run knowhow video transcribe "$V" --classification public  # "N câu" + 10 câu đầu; lần đầu tải Whisper
ID=VID-…                                                      # video_id in ở dòng đầu của `video segment`
uv run knowhow vlm describe "$ID" --no-consistency            # lượt A + C; bỏ cờ này để chạy cả lượt B (gấp đôi thời gian)
uv run knowhow vlm propose-reasons "$ID"
```

- `vlm describe <video_id>` đọc `segments.json` và `transcript.json` của spec 03. Lối tắt `vlm describe --video FILE`
  **không** tạo transcript và mặc định cắt `fixed_window`, nên không dùng được để kiểm lý do.
- Hồ sơ nháp vào profile store `data/work/profiles.sqlite` (`KNOWHOW_PROFILE_SINK=auto`), nên thấy được trên UI.
  File tạm của từng lượt nằm trong `data/work/vlm/<video_id>/describe-local_openai/`: `pass_a/` (câu trả lời thô,
  có `usage` token), `pass_c.json`, `predictions.json`, `profiles.json` (bản **trước** khi đề xuất lý do), và
  `failed_segments.json` nếu có đoạn lỗi.
- Kiểm BR-02 trên bản trước khi đề xuất lý do (mọi dòng phải in `vi phạm: không`):

  ```bash
  uv run python - <<'PY'
  import glob, json
  for f in glob.glob("data/work/vlm/*/describe-local_openai/profiles.json"):
      ps = json.load(open(f, encoding="utf-8"))
      bad = [p["profile_id"] for p in ps if p.get("reason") or p.get("reason_source") or p["status"] != "draft"]
      print(f, len(ps), "profile, vi phạm:", bad or "không")
  PY
  ```

- Kiểm sau khi đề xuất lý do: chỉ bước có `transcript_excerpt` mới có thể có `reason`. Mỗi `reason` phải là một
  phần lời chuyên gia trong excerpt của chính bước đó, `reason_source = expert_verbal`, `status = in_review`.

  ```bash
  uv run python -c "from mentormind.knowledge_base.store.profile_store import ProfileStore as S; [print(p.profile_id, p.status, repr(p.reason), '|', (p.evidence.transcript_excerpt or '')[:80]) for p in S(db_path='data/work/profiles.sqlite').list_profiles(process_id='PACK01')]"
  ```

→ QWEN-04, QWEN-09, QWEN-10, QWEN-13.

**Q2 — Tri thức + trợ lý bằng CLI (cần Docker).** Máy có Postgres ở cổng 5432 thì dùng cổng 5433 (§4.2).

```bash
docker compose --profile lite up -d postgres neo4j        # chờ healthy: docker compose ps
uv run knowhow kg init                                    # Neo4j schema initialized
uv run knowhow kg load-sigma --classification synthetic   # Loaded 6 Sigma lots
uv run knowhow ingest run --input data/demo/packing/packing_sop.pdf --classification synthetic
uv run knowhow ingest index                               # lần đầu tải bge-m3 (~2,2 GB)

# Duyệt hồ sơ của Q1: trên UI (Q3), hoặc qua API đang chạy (§4.3)
curl -s -X POST http://localhost:8000/profiles/WP-PACK01-0xx/review \
  -H 'Content-Type: application/json' -d '{"action":"approve","reviewer":"Tester"}'
uv run knowhow kg stats                                   # "Step" = số bước đã approve

uv run knowhow agent ask "Nếu phát hiện pin connector bị cong thì phải làm gì?" --process PACK01
uv run knowhow agent ask "Nhặt sản phẩm từ băng tải như thế nào?" --process PACK01   # đổi theo tên bước đã approve
uv run knowhow agent ask "Giá cổ phiếu DENSO hôm nay là bao nhiêu?" --process PACK01
uv run knowhow agent rca --lot LOT-PACK01-001
uv run knowhow agent rca --lot LOT-KHONG-CO               # exit 1: "không tìm thấy lot"
```

- `agent ask` in câu trả lời, các dòng `[n] <source_type> <ref_id>: …` và `độ tin cậy`. Khi từ chối thì in câu từ
  chối, kèm `Hỏi chuyên gia: …` nếu process có chuyên gia.
- Mỗi lần gọi agent ghi một dòng JSON vào `data/work/traces/`: `max_rrf`, `max_cosine`, `blocked_by`
  (`rrf` | `cosine` | `llm_unanswerable` | `post_check`, hoặc `null` khi đã trả lời). Câu ngoài phạm vi thường bị chặn ở
  cổng cosine (`KNOWHOW_ASSIST_MIN_COSINE=0.40`), không tốn lượt trả lời. Số còn lại do Qwen tự từ chối
  (`llm_unanswerable`).
- `kg load-profiles` chỉ nạp profile `approved` (bỏ qua bản nháp), nên không dùng được để đi tắt qua bước duyệt.

→ QWEN-11, QWEN-05 (bản CLI).

**Q3 — API + UI ở chế độ `live`.** Làm theo [setup.md](setup.md) §3–§5 với ba khác biệt khi Qwen chạy trên chính máy này:
`KNOWHOW_VLM_BASE_URL` để rỗng, `KNOWHOW_LOCAL_HOSTS=[]`, và cấu hình đường B của §4.4.2. Đặt thêm
`KNOWHOW_API_AGENTS=live`, rồi khởi động lại uvicorn. Dùng clip 30 s của Q1 cho Luồng B. Không tắt API khi job
đang chạy: job sẽ thành `failed` (spec 08 AC-17). → QWEN-05, QWEN-06, QWEN-07, QWEN-12.

**Q4 — Đánh giá (khói).** Chưa có `data/golden_set/qa.jsonl`, nên dùng fixture 5 câu để kiểm đường ống chạy được.
Đây **không** phải số liệu cho báo cáo: `expected_citations` của fixture trỏ tới profile mẫu, không phải profile
trong KB của bạn.

```bash
uv run knowhow eval ragas --golden tests/fixtures/eval/qa_5.jsonl --classification synthetic
uv run knowhow eval review-stats
uv run knowhow eval report                 # data/work/eval/usefulness_report.md
```

→ QWEN-14. Lượt cho báo cáo nộp làm theo EVAL-01…03.

#### 4.4.4 Quay lại giả lập để chạy test

Test tự động không gọi Qwen, nhưng **cấu hình trong `.env` hay shell vẫn lọt vào test**. Đo ngày 07/10 trên `38f94ec`:

| Cấu hình đặt | Kết quả `pytest` |
|---|---|
| `.env` như `.env.example` (`mock`, `builtin`, `local_openai`) | Xanh, 605 pass |
| `KNOWHOW_VLM_PROVIDER=local_openai`, `KNOWHOW_VLM_MODEL=…` | Vẫn xanh |
| `KNOWHOW_API_AGENTS=live` (đã thử trong shell; `.env` cho kết quả tương tự vì test API đọc `.env`) | 4 test fail: `tests/test_api_endpoints.py::test_assistant_ask` (503), `::test_rca_investigate_valid_lot`, `::test_ac_06_rca_invalid_lot_not_found`, `tests/backend/app/routers/test_videos.py::test_ac_15_the_lots_are_the_sigma_adapters_and_rca_finds_each` |
| `KNOWHOW_EVAL_JUDGE=builtin` **trong shell** | 1 fail: `test_the_ragas_package_is_the_default_judge`. Trong `.env` thì không ảnh hưởng (test dùng `_env_file=None`) |

Khi `.env` đang trỏ Qwen và `live`, chạy test bằng biến shell ghi đè (đã thử 07/10: `make check` xanh, 605 pass):

```bash
KNOWHOW_API_AGENTS=mock KNOWHOW_EVAL_JUDGE=ragas make check
```

#### 4.4.5 Lỗi thường gặp khi chạy với Qwen

| Triệu chứng | Nguyên nhân | Xử lý |
|---|---|---|
| `HTTP 400 … exceed_context_size_error … (8409 tokens) exceeds … (4096 tokens)` | Model Ollama mặc định chỉ có context 4096 | Tạo model `num_ctx` lớn (§4.4.1) và đặt `KNOWHOW_VLM_MODEL` |
| Ping PASS nhưng `vlm describe` hoặc job video lỗi HTTP 400 `exceed_context_size_error` | `KNOWHOW_VLM_MAX_FRAMES=40` từ `.env.example`; ping không đọc biến này | Đặt `KNOWHOW_VLM_MAX_FRAMES=8` (đường B), hoặc dùng đường A |
| Có `failed_segments.json`, hoặc câu trả lời thô trong `pass_a/` bị cụt | Token vào + "nghĩ" vượt `num_ctx` (7 khung đã dùng 87% của 16k) | Giảm `KNOWHOW_VLM_MAX_FRAMES` xuống 6, hoặc dùng đường A |
| `Lỗi: Cần ffmpeg trong PATH để cắt clip (spec 03 FR-06)` | Chưa cài ffmpeg | `brew install ffmpeg` |
| Log `Không có ffprobe: đọc … bằng OpenCV, coi như không có audio`; transcript rỗng | Thiếu `ffprobe`, nên video bị coi là câm | Cài ffmpeg (có kèm ffprobe), rồi chạy lại `video probe`: phải thấy `"has_audio": true` |
| `Lỗi: … Connection refused` | Ollama chưa chạy, hoặc sai `KNOWHOW_VLM_BASE_URL` | `ollama serve`; kiểm `curl http://127.0.0.1:11434/api/version` |
| 404 `model '…' not found` | Chưa `ollama pull`/`ollama create`, hoặc sai tên trong `KNOWHOW_VLM_MODEL` | `ollama list`, rồi sửa tên |
| Mỗi lượt VLM mất 2–9 phút | Qwen3-VL Q4 "nghĩ" trước khi trả lời (ping 116 s, lượt A 518 s) | Bình thường. Giữ `KNOWHOW_VLM_TIMEOUT_S` ≥ 900 (`.env.example`: 1800). Kiểm bằng clip 30 s và `--no-consistency` |
| `ollama ps` không hiện `100% GPU` | Context quá lớn so với RAM, model tràn sang CPU | Giảm `num_ctx` hoặc số khung; đóng ứng dụng khác |
| Câu hỏi trợ lý/RCA treo vài phút khi job video đang chạy | Ollama xử lý từng request một | Chờ job xong rồi hỏi, hoặc hỏi trước khi upload video |
| `Lỗi: Không kết nối được PostgreSQL … role "knowhow" does not exist` | Cổng 5432 đang do một Postgres khác giữ (ví dụ Homebrew `postgresql@16`) | Đổi cổng container: `KNOWHOW_PG_PORT=5433` và `KNOWHOW_PG_DSN=…:5433/knowhow` (§4.2) |
| API trả 503 `Agent chưa sẵn sàng: …` | `KNOWHOW_API_AGENTS=live` nhưng Neo4j, vector store hoặc LLM chưa lên | `docker compose --profile lite up -d postgres neo4j`, `knowhow kg init`, bật Ollama |
| Trợ lý trên UI vẫn trả câu "…cầm hai mép carton để tránh rách cạnh…" | API đang ở `mock`, hoặc chưa khởi động lại sau khi sửa `.env` | Đặt `KNOWHOW_API_AGENTS=live`, khởi động lại uvicorn |
| Job video `failed` "Máy chủ API đã khởi động lại khi job đang chạy…" | API bị tắt hoặc `--reload` khởi động lại giữa chừng | Chạy uvicorn không có `--reload`, rồi tải video lên lại |
| UI thấy `WP-PACK01-001..004` dù chưa upload gì | `make start` đã seed profile giả | Dùng uvicorn + `npm run dev` (§4.3), làm lại từ `data/work` sạch |
| `Missing option '--input'.` khi `knowhow ingest run <thư mục>` | Lệnh nhận `--input`, không nhận tham số vị trí | `knowhow ingest run --input <file hoặc thư mục> --classification …` |
| `ModuleNotFoundError: langchain_core`, nhiều fail trong `tests/evaluation/ragas/` | venv chưa cài extra `eval` | `uv sync --all-extras` (§4.1) |

## 5. Dữ liệu kiểm thử

| Bộ dữ liệu | Đường dẫn | Dùng cho | Trạng thái 07/10 |
|---|---|---|---|
| Fixture VLM | `tests/fixtures/vlm/` | Spec 04 | Có |
| Khung hình tổng hợp | fixture `frames` trong `tests/conftest.py` | Sampler, guard | Có |
| Sigma mock | `data/mock_sigma/` (6 lot, 5 của PACK01) | Spec 05/07, RCA | Có |
| Video LASI (public, có tiếng Thái) | `data/video/LASI … [m4icg6FgTBU].mkv`, 31 phút | §4.4 Q1, Q3; `vlm sweep` | Có, qua Git LFS (51 MB). Nếu chỉ thấy file con trỏ vài trăm byte: `git lfs pull` |
| Ground truth LASI | `data/video/groundtruth.json` | `vlm sweep` (`docs/reports/c2-vlm-smoke-and-fps-sweep.md`) | Có |
| Tài liệu mẫu | `data/samples/docs/` (`packing_sop.pdf`, `packing_sop_scan.pdf`, `sps_form_12_1_14.xlsx`) | Spec 02 AC-01…03 | Có |
| SOP demo PACK01 | `data/demo/packing/packing_sop.pdf` (3 trang, 13 chunk) | §4.4 Q2, setup.md Luồng A | Có |
| Golden set khói | `tests/fixtures/eval/qa_5.jsonl` (5 câu) | §4.4 Q4 | Có (chỉ để kiểm đường ống) |
| Case PACK01 C1–C5 | `data/samples/packing/case_00x/` | E2E | Chưa có |
| `review_decisions.json` | `data/samples/` | `make demo` bước 4 | Chưa có |
| Golden set | `data/golden_set/qa.jsonl` | Spec 09 | Chưa có |

**Checklist khi nhận dữ liệu mẫu từ BA:**
- Mỗi case có `metadata.json` với `data_classification` là `synthetic` hoặc `public`, và có `case_id`.
- `expected/work_profile.json` qua được `validate_against_contract`.
- Có đủ C1–C5 theo PRD §6. Riêng C2 phải thật sự không có track audio (`ffprobe` không thấy stream audio, hoặc
  `knowhow video probe` in `"has_audio": false`).
- Ground truth do BA viết và có người thứ hai kiểm tra, không chép từ output của model.

**Checklist golden set:**
- Có ≥ 30 câu, đúng phân bố how 10 / why 6 / exception 5 / relational 5 / out_of_scope 4.
- Mỗi `expected_citations` trỏ tới một `profile_id` sẽ ở trạng thái `approved` sau `review_decisions.json`.
- Câu `out_of_scope` phải thật sự nằm ngoài dữ liệu.
- Validator (spec 09 AC-01) chạy không lỗi.

## 6. Ma trận phủ Acceptance Criteria (07/10/2026)

Cột "Test tự động" đếm theo tên `test_ac_xx` trong thư mục test của module, trên `main` @ `38f94ec`. Riêng spec 01
và spec 05 giữ số của mốc 04/10.

| Spec | AC | Test tự động trên `main` | Chưa thấy test mang tên | Kiểm thủ công |
|---|---|---|---|---|
| 01 | 01–11 | 03–11 | — | AC-01 (clone mới, CI), AC-02 (`make up`) |
| 02 | 01–18 | 01–05, 08–11, 14, 15 (`tests/capture/ingest/`); 06, 12, 13, 15, 16 (`tests/knowledge_base/store/`, phần pgvector chạy ở §4.2) | 17, 18 | AC-07 (`docs/data/sample_review.md`) |
| 03 | 01–16 | 01–16 | — | Video thật với ffmpeg + Whisper (§4.4 Q1) |
| 04 | 01–23 | 01–14, 16–23 (AC-14 trong `tests/infra/`) | — | AC-15 (Ollama/GPU, QWEN-01) |
| 05 | 01–11 | 10, 11 theo tên; 01, 03, 05, 06, 09 bằng test đặt tên mô tả | 02 (nạp lại không đổi số node/cạnh), 07 (câu không liên quan thì không chọn template); AC-08 luôn skip | AC-08 trên Neo4j (§4.2) |
| 06 | 01–12 | 01–12 | — | Agent với Qwen thật (QWEN-05, QWEN-11) |
| 07 | 01–06 | AC-06 phủ một phần (`test_committed_sigma_fixture_is_case_and_time_linkable`) | 01–05 (`knowhow sigma gen-mock` chưa có) | — |
| 08 | 01–18 | 01–04, 06, 09–18 (AC-16 trong `tests/agents/adapters/test_rest.py`) | 05 (job lỗi trả `failed`; AC-12, AC-14 có phủ trường hợp này cho job tài liệu và video) | AC-07 (`make demo`), AC-08 (UI) |
| 09 | 01–07 | 01–07 | — | EVAL-01…03 |

**Quy ước truy vết.** Tên `test_ac_xx` không chứa số spec, nên cùng một tên có thể thuộc nhiều spec (ví dụ
`test_ac_08` thuộc spec 01 trong `tests/knowledge_base/store/test_vector_store.py`). Hiện phải truy theo đường dẫn
file. Đề xuất: mọi test AC mới có docstring `"""Spec NN AC-xx."""`. Các test đặt tên mô tả nhưng đang phủ AC
(chủ yếu ở spec 05) cũng nên được thêm docstring như vậy.

## 7. Test case thủ công và E2E

Ưu tiên: **P1** phải pass mới được nộp; **P2** nên pass, nếu fail thì ghi vào phần "Hạn chế" của báo cáo.
Ghi kết quả từng lượt chạy vào issue hoặc PR, kèm commit hash.

### 7.1 Luồng chính (PRD §11)

| ID | Truy vết | Bước | Kết quả mong đợi | Ưu tiên |
|---|---|---|---|---|
| E2E-01 | PRD-AC-01, spec 08 AC-07, NFR-05 | Clone mới, không có `.env`; pull image docker trước rồi ngắt mạng; chạy `KNOWHOW_DEMO_OFFLINE=1 make demo` | Exit 0, toàn luồng ≤ 5 phút, không có lời gọi ra ngoài | P1 |
| E2E-02 | PRD-AC-08 | Lấy case C1: video → `segment_id` (`VID-…-SNNN`) → `evidence.segment_ids` của profile → citation trong câu trả lời → bấm mở nguồn | Mỗi mắt xích trỏ đúng mắt xích kế tiếp; clip mở đúng `t_start` | P1 |
| E2E-03 | US-04, PRD-AC-04 | Hỏi "Bước 3 làm thế nào?" | Có ≥ 1 citation; mỗi marker `[n]` có citation tương ứng; citation trỏ tới profile `approved` | P1 |
| E2E-04 | US-05, BR-02 | Hỏi "Vì sao…?" cho một bước có `reason` đã duyệt, rồi cho một bước có `reason = null` | Bước thứ nhất: trả đúng `reason` kèm citation. Bước thứ hai: không bịa lý do (bỏ phần lý do, hoặc từ chối kèm gợi ý chuyên gia) | P1 |
| E2E-05 | US-06, BR-05, NFR-07 | Hỏi câu ngoài phạm vi, ví dụ "Lịch nghỉ lễ tháng sau thế nào?" | `refused = true`, có gợi ý người cần hỏi khi process có chuyên gia | P1 |
| E2E-06 | PRD-AC-03, BR-01 | Reject 1 profile, để 1 profile ở `draft`; hỏi câu khớp đúng nội dung của hai profile đó | Hai profile này không xuất hiện trong citation; `knowhow kg stats` không tăng | P1 |
| E2E-07 | Spec 08 AC-01 | Sửa một profile đã `approved` | `version` + 1, `status = in_review`; trong lúc chưa duyệt lại, assistant vẫn trích bản cũ | P1 |
| E2E-08 | PRD-AC-02, case C2 | Chạy `describe` trên video câm (kiểm trước bằng `video probe`: `"has_audio": false`) | Mọi profile có `reason = null` và `reason_source = null` | P1 |
| E2E-09 | PRD-FR-03, spec 04 AC-08/09/22 | Case C1 có lời chuyên gia → `video transcribe`, `vlm describe <video_id>`, `vlm propose-reasons` (§4.4 Q1) | `reason` khớp nguyên ý phát ngôn, `reason_source = expert_verbal`, `status = in_review`; câu không có trong transcript thì `reason` giữ null | P1 (spec 03 đã merge, PR #18) |
| E2E-10 | PRD-FR-09, spec 06 AC-05/07 | RCA với lot mock có defect `D-03` | ≤ 3 giả thuyết; giả thuyết `high`/`medium` có evidence; `five_why` có 3–5 bước, bước không có căn cứ ghi `verified = false`; có disclaimer | P2 |
| E2E-11 | Spec 08 AC-06, spec 06 AC-06 | RCA với `lot_id` không tồn tại | API trả 404; UI báo lỗi bằng tiếng Việt | P2 |
| E2E-12 | Case C3 | Chạy `describe` trên case có ngoại lệ | `exceptions` có đủ `case` và `handling` | P2 |
| E2E-13 | Case C4, C5 | Chạy trên case mơ hồ hoặc mâu thuẫn | `confidence` thấp, profile nằm trong hàng đợi duyệt, không có gì tự publish | P2 |

### 7.2 Evaluation

| ID | Truy vết | Bước | Kết quả mong đợi | Ưu tiên |
|---|---|---|---|---|
| EVAL-01 | PRD-AC-06, NFR-04, spec 09 FR-04/05 | `knowhow eval ragas` rồi `knowhow eval report` | `usefulness_report.md` có: bảng chỉ số với cột "Đạt ngưỡng" ✅/❌, 5 câu tệ nhất, bảng "Profile cần xem lại", phần Hạn chế và thiết kế pilot. `summary.json` có `run_id`, thời điểm, model, commit hash | P1 |
| EVAL-02 | Spec 09 FR-02 | Kiểm judge của lượt chạy dùng cho báo cáo nộp | Judge là model mạnh (không phải model khoảng 8B) và được ghi trong báo cáo | P1 |
| EVAL-03 | BRD §11 | Đối chiếu từng con số trên slide với `summary.json` | Mọi số khớp một `run_id` cụ thể; chỉ số pilot (nhóm C) chỉ trình bày thiết kế, không có số | P1 |
| EVAL-04 | Spec 09 nhóm A | `knowhow eval review-stats` | Có tỷ lệ approve không sửa / approve sau sửa / reject; `reason_coverage.synthetic ≥ 0.6` | P2 |
| EVAL-05 | Spec 04 AC-07 | `knowhow vlm sweep` trên video LASI | CSV đủ cột; so với mốc trong `docs/reports/c2-vlm-smoke-and-fps-sweep.md`, sụt rõ rệt thì mở lỗi | P2 |

### 7.3 Bảo mật và dữ liệu (tất cả P1)

| ID | Truy vết | Bước | Kết quả mong đợi |
|---|---|---|---|
| SEC-01 | PRD-AC-05, BR-04, spec 04 AC-03 | Đặt `KNOWHOW_VLM_PROVIDER=openrouter` (key giả), chạy `knowhow vlm describe --video <clip> --classification factory_confidential` | `ConfidentialDataError` trước khi đọc file; không có request nào đi ra |
| SEC-02 | Spec 04 AC-13 | `local_openai` với `KNOWHOW_VLM_BASE_URL` trỏ tới host public; sau đó trỏ tới `localhost` hoặc IP LAN | Host public bị coi là cloud và dữ liệu mật bị chặn; localhost/LAN được coi là local |
| SEC-03 | Spec 06 AC-04 | LLM cloud, context chứa một passage `factory_confidential` | Passage đó không có trong prompt gửi đi |
| SEC-04 | Spec 04 AC-16/17 | Gửi prompt có số điện thoại và khung hình có mặt người tới provider cloud | Prompt đã che (`[PHONE_1]`), mặt bị làm mờ, audit chỉ ghi số lượng; thiếu model làm mờ thì từ chối gửi |
| SEC-05 | Spec 08 AC-04 | `curl -i http://127.0.0.1:8000/media/../../etc/passwd`, sau đó thử bản mã hóa `%2e%2e%2f` | 400 hoặc 404, không trả nội dung file |
| SEC-06 | Spec 01 AC-06, constitution Điều 2 | Sau một lượt demo, chạy `git status` | Không có video/audio ngoài `data/samples/` và `data/video/` (LFS), không có `.env`, không có gì từ `data/work/` |
| SEC-07 | Spec 04 FR-09, constitution Điều 6 | Chạy với key sai hoặc URL có basic-auth | Thông báo lỗi và log không in ra key hay mật khẩu |
| SEC-08 | Spec 08 FR-05 | Gọi API từ một origin khác origin đã cấu hình | Trình duyệt chặn CORS |

### 7.4 UI tablet

Viewport cần thử: 1024×768 và 768×1024 (Chrome DevTools); thêm một máy tablet thật nếu có.

| ID | Truy vết | Kiểm | Kết quả mong đợi | Ưu tiên |
|---|---|---|---|---|
| UI-01 | NFR-06 | Cỡ chữ, nút bấm | Chữ ≥ 16px; nút đủ lớn để bấm bằng ngón tay (đề xuất ≥ 44px) | P1 |
| UI-02 | NFR-06, CLAUDE.md | Toàn bộ text hiển thị | Tiếng Việt. **Lỗi đã biết**, xem §11 | P1 |
| UI-03 | Spec 08 AC-08 | Nhập `reason` nhưng không chọn `reason_source` | Nút Duyệt bị vô hiệu và có thông báo (hiện đã đúng hành vi, nhưng thông báo là tiếng Anh) | P1 |
| UI-04 | PRD §10 Screen 1 | Màn duyệt | Hiện 3 keyframe, clip, step, hand_action, key_point, reason + nguồn, exceptions, pass_criteria, evidence | P1 |
| UI-05 | Spec 08 AC-03, PRD-FR-05 | Reject không nhập comment | Bị chặn; chọn được error_tags | P1 |
| UI-06 | PRD-AC-07 | Mở một profile đã `approved` | Thấy người duyệt và thời điểm duyệt | P1 |
| UI-07 | PRD §10 Screen 2 | Bấm vào citation | Video tua tới `t_start`; tài liệu hiện đoạn trích | P1 |
| UI-08 | PRD §10 Screen 3 | Màn RCA | Phân biệt rõ bước 5-Why `verified` và chưa xác minh; luôn có disclaimer | P2 |
| UI-09 | — | Tắt API rồi thao tác trên UI | Thông báo lỗi thân thiện bằng tiếng Việt, không lộ stack trace | P2 |
| UI-10 | — | Tải lại trang giữa lúc đang duyệt | Kết quả duyệt đã lưu không bị mất | P2 |

### 7.5 Độ bền

| ID | Truy vết | Bước | Kết quả mong đợi | Ưu tiên |
|---|---|---|---|---|
| RES-01 | Spec 08 AC-05 | VLM báo lỗi khi đang xử lý video | `GET /jobs/{id}` trả `failed` kèm message; server vẫn phục vụ request khác | P1 |
| RES-02 | Spec 04 AC-06 | Một segment trả JSON lỗi 2 lần liên tiếp | Segment đó vào `failed_segments.json`; các segment khác vẫn có kết quả | P2 |
| RES-03 | Spec 05 AC-10 | Tắt router LLM | Retrieval vẫn trả kết quả vector + expansion | P2 |
| RES-04 | — | Tắt Neo4j hoặc Postgres rồi bấm approve | Lỗi rõ ràng; profile không bị ghi `approved` nửa vời | P2 |
| RES-05 | — | Chạy `knowhow vlm ping` khi Ollama/vLLM chưa bật | Báo lỗi kết nối rõ ràng, không treo | P2 |

### 7.6 Chạy với Qwen3-VL thật (Ollama local)

Chạy sau khi server đã lên (§4.4.1) và cấu hình đã chuyển (§4.4.2), theo các mức ở §4.4.3. Chỉ dùng dữ liệu
`public`/`synthetic`. Cột "Kết quả gần nhất" chỉ ghi những gì thật sự đã chạy (máy kiểm: Mac M4 16 GB, Ollama
0.35.1, đường B). Ô "Chưa" là quy trình chưa có kết quả.

| ID | Truy vết | Bước | Kết quả mong đợi | Ưu tiên | Kết quả gần nhất |
|---|---|---|---|---|---|
| QWEN-01 | Spec 04 AC-15 | Q0: `uv run knowhow vlm ping --frames 8` | Dòng đầu `provider=local_openai … cloud=False`; dòng cuối `PASS`; exit 0 | P1 | 07/10 @ `38f94ec`: PASS, 116,5 s, 8409 vào / 364 ra, 100% GPU |
| QWEN-02 | RES-05 | Ollama đã tắt, hoặc `KNOWHOW_VLM_BASE_URL` trỏ cổng không có server, rồi `vlm ping` | `Lỗi: …` bằng tiếng Việt kèm nguyên nhân kết nối, exit 1, không treo | P2 | 05/10: lỗi sau khoảng 8 s |
| QWEN-03 | Chống chạy nhầm cấu hình | `KNOWHOW_VLM_MODEL=qwen3-vl:8b` (context 4096), `vlm ping --frames 8` | Báo lỗi `exceed_context_size_error` rõ ràng, exit 1; không có kết quả giả PASS | P2 | 05/10: HTTP 400 |
| QWEN-04 | PRD-AC-02, BR-02, E2E-08 | Q1: `video segment` → `vlm describe <video_id> --no-consistency` trên clip public/synthetic | Hồ sơ nháp vào profile store; `profiles.json` trong `describe-local_openai/` có mọi bước `status = draft`, `reason = null`, `reason_source = null`; tên bước tiếng Việt; không có `failed_segments.json` | P1 | Chưa chạy qua CLI: máy kiểm thiếu ffmpeg. 07/10 chạy lượt A trên 1 đoạn LASI bằng script: 2 bước tiếng Việt, 0 đoạn lỗi, 518 s (§4.4.1) |
| QWEN-05 | PRD-AC-04, §11 (S2) | Q3: `KNOWHOW_API_AGENTS=live`, KB đã nạp (Q2); `POST /assistant/ask` hoặc tab **KNOW-HOW ASSISTANT** với câu về bước đã approve | Câu trả lời **không còn** là câu mock viết cứng; citation trỏ tới profile `approved` hoặc chunk có thật trong KB, thẻ **BƯỚC THAO TÁC** có keyframe và thời điểm | P1 | Chưa (Docker không chạy trên máy kiểm) |
| QWEN-06 | Spec 08 AC-06, E2E-11 | Như QWEN-05, nhưng `POST /rca/investigate` với `lot_id` không tồn tại | 404, thông báo tiếng Việt | P2 | Chưa |
| QWEN-07 | RES-04 | `KNOWHOW_API_AGENTS=live` khi Neo4j/Postgres/Ollama chưa lên, gọi `/assistant/ask` | 503 `Agent chưa sẵn sàng: …`, không lộ stack trace | P2 | Chưa (CLI `agent ask` báo lỗi Postgres rõ ràng, chưa thử qua API) |
| QWEN-08 | Hồi quy cấu hình | Với `.env` trỏ Qwen và `KNOWHOW_API_AGENTS=live`: `KNOWHOW_API_AGENTS=mock KNOWHOW_EVAL_JUDGE=ragas make check` | Xanh (§4.4.4) | P1 | 07/10 @ `38f94ec`: xanh, 605 pass, 23 skip. Không ghi đè thì 4 fail (§4.4.4) |
| QWEN-09 | Chống chạy nhầm cấu hình, §4.4.1 | Model 16k với `KNOWHOW_VLM_MAX_FRAMES=40`, chạy `vlm describe` trên clip 30 s | Đoạn ít khung vẫn chạy; tới đoạn đầu tiên giữ nhiều khung thì exit 1, báo HTTP 400 `exceed_context_size_error`; store không có profile mới của video đó (chỉ lưu khi cả pipeline xong) | P2 | Chưa |
| QWEN-10 | Spec 04 AC-08/09/22, BR-02, E2E-09 | Q1: `vlm propose-reasons <video_id>` sau `video transcribe` | Chỉ bước có `transcript_excerpt` mới có thể có `reason`; `reason` là một phần lời trong excerpt của chính bước đó; `expert_verbal`, `in_review`; bước khác giữ `draft`, `reason = null` | P1 | 07/10: chạy `propose_reasons` bằng script trên 2 profile tổng hợp: đúng cả hai trường hợp (§4.4.1). Chưa chạy trên transcript LASI thật |
| QWEN-11 | Spec 06, PRD-AC-04, BR-05 | Q2: `agent ask` (câu trong SOP, câu về bước đã approve, câu ngoài phạm vi), `agent rca --lot LOT-PACK01-001`, `agent rca --lot LOT-KHONG-CO` | Hai câu đầu có `[n]` khớp citation; câu ngoài phạm vi bị từ chối (trace có `blocked_by` = `cosine` hoặc `llm_unanswerable`); RCA in JSON có ≤ 3 giả thuyết, 5-Why và disclaimer; lot lạ exit 1 | P1 | Chưa |
| QWEN-12 | Spec 08 AC-14/18, PRD §11 | Q3: setup.md Luồng B với clip 30 s và Qwen local | Job đi qua 5 giai đoạn rồi **HOÀN TẤT**; bảng bước có trạng thái **NHÁP**/**ĐANG DUYỆT**; approve 1 bước thì `kg stats` tăng 1 `Step` | P1 | Chưa |
| QWEN-13 | Tiền điều kiện, E2E-08/09 | Trước Q1: `ffprobe -version`, rồi `video probe` trên LASI | ffprobe có trong PATH; LASI có `"has_audio": true`. Thiếu ffmpeg thì `video segment` dừng với `Lỗi: Cần ffmpeg…`, exit 1 | P1 | 07/10: máy kiểm thiếu ffmpeg; `video segment` và `vlm describe --video` dừng đúng thông báo, exit 1; `probe` rơi về OpenCV, coi video là câm |
| QWEN-14 | Spec 09, EVAL-01 (khói) | Q4: `eval ragas --golden tests/fixtures/eval/qa_5.jsonl --classification synthetic`, `eval review-stats`, `eval report` | Có `ragas_results.csv`, `summary.json` (có `run_id`, model, commit), `usefulness_report.md`; không dùng số này cho slide | P2 | Chưa |
| QWEN-15 | Spec 04 AC-23 | `KNOWHOW_LOCAL_HOSTS=["<tên>.ngrok-free.dev"]` với `KNOWHOW_VLM_BASE_URL` ngrok; sau đó xóa dòng `LOCAL_HOSTS` | Có khai báo: lệnh Python ở §4.4.2 in `local`. Xóa khai báo: in `cloud`, và `vlm describe --classification factory_confidential` bị `ConfidentialDataError` | P2 | Chưa (phủ bằng test tự động spec 04 AC-23) |

## 8. Hồi quy khi merge nhánh lớn

Hai nhánh mà bản 1.0 chờ đã vào `main`: `viethoang/ingest-index` (PR #10) và `phuc-nguyen/agents-eval-on-main`
(PR #12). Nhánh `viethoang/ingext-index-trungntresolve` còn 1 commit không có trên `main` (`cd93d97`); chủ nhánh cần
xác nhận là bỏ commit đó. Giữ các bước dưới làm checklist cho lần merge nhánh lớn tiếp theo:

1. `uv sync --all-extras && make check`. Kỳ vọng 0 fail, số test ≥ mốc ở §4.1 cộng phần test mới.
2. Mọi lệnh con mới có `--help` (`knowhow <nhóm> --help`).
3. Gọi `/assistant/ask` ở `live`: câu trả lời **không** là câu mock viết cứng ("…cầm hai mép carton để tránh
   rách cạnh…"); citation trỏ tới profile hoặc chunk có thật trong KB. Khi từ chối, `suggested_expert` của API
   lấy từ `suggested_contact` của agent (`mentormind/agents/adapters/rest.py`).
4. `grep -rnE "store\.pgvector([^_]|$)|store\.embedding([^_]|$)" mentormind tests`: không được có import mới tới hai
   module cũ (§11).
5. Chạy integration ở §4.2 cùng test pgvector. Không được có skip ngoài ý muốn.
6. `KNOWHOW_VECTOR_BACKEND=memory` vẫn chạy được mà không cần docker (spec 01 AC-08).
7. Chạy `knowhow ingest run --input data/samples/docs --classification synthetic` hai lần. Số dòng JSONL và
   `chunk_id` không đổi (spec 02 AC-04).
8. Chạy `make demo` và ghi lại các mục preflight còn `[ ]`.

## 9. Tiêu chí vào/ra cho bản nộp 12/10

**Điều kiện bắt đầu test hệ thống:**
- Preflight `make demo` xanh.
- Có ít nhất case C1, C2 và golden set.

**Điều kiện được phép nộp:**
- `make check` và CI xanh trên commit nộp.
- Integration (§4.2) đã chạy ít nhất một lần trên commit nộp, 0 fail, kết quả đính kèm PR.
- E2E-01 pass 3 lần liên tiếp trên máy sạch, mỗi lần ≤ 5 phút.
- Mọi test case P1 ở §7 pass. Không còn lỗi S1 hoặc S2 đang mở.
- Báo cáo evaluation sinh từ chính commit nộp. Chỉ số không đạt ngưỡng được ghi trung thực, không chỉnh
  tay, và có giải thích trong phần Hạn chế.
- `git status` sạch, không có file dữ liệu bị cấm.

## 10. Báo lỗi

| Mức | Định nghĩa | Ví dụ |
|---|---|---|
| S1 Chặn | Vi phạm constitution, mất dữ liệu duyệt, hoặc `make demo` hỏng | Dữ liệu mật đi ra cloud; `reason` do AI tự điền; profile chưa duyệt xuất hiện trong câu trả lời; câu trả lời không có citation mà không từ chối |
| S2 Nặng | Luồng chính sai, không chấp nhận được khi demo | Citation trỏ sai nguồn; RCA lỗi; duyệt không lưu được |
| S3 Vừa | Sai hiển thị hoặc trải nghiệm, luồng vẫn đi được | Text tiếng Anh cho người dùng; thông báo lỗi khó hiểu |
| S4 Nhẹ | Thẩm mỹ, chính tả | Lệch căn lề, sai dấu |

**Mẫu issue (GitHub):**

```
Tiêu đề: [S2][spec 06 AC-02] Câu trả lời có marker [3] nhưng chỉ có 2 citation
Môi trường: commit <hash>, macOS/Linux, VLM=<provider/model>, LLM=<provider/model>, KNOWHOW_VLM_MAX_FRAMES=<n>, vector=<memory|pgvector>
Dữ liệu: case_id=CASE-PACK01-001, data_classification=synthetic
Bước tái hiện: 1. … 2. … 3. …
Mong đợi: <trích nguyên văn AC/BR/FR>
Thực tế: …
Bằng chứng: log, ảnh chụp, file trong data/work/… (đã che key; không đính kèm dữ liệu mật)
```

## 11. Lỗi đã biết, rủi ro và khoảng trống

**Lỗi đã biết (07/10):**
- **[S2] `make demo` chưa chạy được (E2E-01, PRD-AC-01).** Preflight dừng ở 2 mục: `knowhow sigma gen-mock` (nhóm
  `sigma` mới là chỗ giữ chỗ, spec 07) và `data/samples/review_decisions.json` (spec 08 T08-6). Sửa xong hai mục
  đó, `scripts/demo.sh` vẫn sẽ lỗi ở hai chỗ: `ingest run "$SAMPLES/docs"` (lệnh cần `--input`) và
  `sigma lots` (chưa có lệnh).
- **[S2] `/assistant/ask` và `/rca/investigate` mặc định vẫn trả câu trả lời mock viết cứng.** Router chỉ gọi agent
  thật khi `KNOWHOW_API_AGENTS=live` (§4.4.2), mà mặc định là `mock`. Chỉ kết quả chạy với `live` mới chứng minh được
  PRD-AC-04 (QWEN-05). Chưa có lượt chạy `live` nào được ghi lại.
- **[S3] UI còn text tiếng Anh**, vi phạm NFR-06 và CLAUDE.md. Ví dụ: tên tab **HUMAN-IN-THE-LOOP REVIEW**,
  **KNOW-HOW ASSISTANT**, **ROOT CAUSE ANALYSIS (5-WHY)**; `ReviewProfilesTab.tsx:169` ("AC-08 VIOLATION:
  reason_source must be set before approving."); `AssistantTab.tsx:181` ("Insufficient Evidence — Response
  Refused"). Nên nâng lên S2 nếu demo trước người dùng nhà máy.
- **[S3] Trợ lý trả lời thiếu bước của SOP**: bảng 8 bước không được tìm thấy vì chỉ chunk có chữ "PACK01" mới qua
  bộ lọc công đoạn (setup.md Luồng A; chờ sửa spec 02).
- **[S4] File chết:** `mentormind/core/schemas.py` (bị package `core/schemas/` che mất);
  `mentormind/knowledge_base/store/pgvector.py` và `store/embedding.py` (không module nào import; bản đang dùng là
  `pgvector_store.py` và `embedder.py`).

**Rủi ro và khoảng trống:**
- Chưa có case C1–C5 nên E2E-01, E2E-02, E2E-08 và E2E-09 chưa chạy được trên dữ liệu PACK01. Trong lúc chờ: kiểm
  luồng video bằng LASI (§4.4 Q1), kiểm phần còn lại bằng profile seed (`mentormind/knowledge_base/store/seed_demo.py`).
- Qwen local chậm (một lượt A 518 s trên M4 16 GB), nên một lượt chạy UI với video vài phút mất hàng giờ. Đặt lịch
  chạy QWEN-12 sớm, đừng để tới ngày nộp.
- Máy thiếu `ffprobe` cho ra kết quả "video câm" sai mà không báo lỗi (QWEN-13). Luôn kiểm tiền điều kiện trước khi
  ghi kết quả E2E-08/09.
- CI không chạy integration, nên lỗi Neo4j/pgvector chỉ lộ ra khi chạy tay theo §4.2.
- Frontend không có test tự động; toàn bộ UI dựa vào §7.4. Sau 12/10 nên thêm ít nhất một smoke test
  Playwright cho luồng duyệt.
- Judge Ragas cỡ khoảng 8B chấm không ổn định (spec 09 FR-02). Nếu hai lượt chạy cùng cấu hình lệch nhau
  nhiều, ghi cả hai vào báo cáo.
- Chưa có test mang tên cho spec 02 AC-17/18, spec 05 AC-02/07, spec 07 AC-01…05, spec 08 AC-05 (xem §6).

## Changelog
- v1.2 (07/10/2026): §4.4 viết lại cho kiểm thử với Qwen local: bảng "Qwen được gọi ở đâu"; chuẩn bị máy (ffmpeg bắt
  buộc, thiếu ffprobe thì video bị coi là câm); chọn context theo lượt A thật (7 khung = 7941 vào / 6348 ra, 518 s),
  `vlm ping` không đọc `KNOWHOW_VLM_MAX_FRAMES`; các mức Q0–Q4 bằng CLI/API/UI; bảng công tắc thêm `KNOWHOW_LOCAL_HOSTS`,
  `KNOWHOW_VIDEO_METHOD`, `KNOWHOW_ASR_*`, timeout; §4.4.4 đo lại (`live` → 4 fail, `builtin` chỉ fail khi đặt ở shell);
  lỗi thường gặp thêm 9 dòng. §7.6 thêm QWEN-09…15. §4.1 mốc 605 pass / 23 skip. §4.3 cảnh báo `make start`, CORS,
  khởi động lại API. §5, §6 cập nhật theo `main` @ `38f94ec` (spec 03 đã merge). §8: hai nhánh đã merge, sửa
  `ingest run --input`. §11: thêm lỗi `make demo`, SOP thiếu bước, file chết pgvector/embedding.
  Đã chạy thật: `make check`, `pytest` với các cấu hình ở §4.4.4, `vlm ping`, lượt A trên 1 đoạn LASI và
  `propose_reasons` với Qwen (bằng script, vì máy kiểm thiếu ffmpeg), preflight `make demo`, lỗi thiếu ffmpeg. Chưa
  chạy: Q1 qua CLI, Q2–Q4 (Docker không chạy), đường A (submodule trống).
- v1.1 (05/10/2026): §4.4 viết lại: chạy Qwen3-VL bằng Ollama (đường A script, đường B Ollama thuần), cách chuyển
  source sang Qwen, ảnh hưởng của cấu hình lên test, lỗi thường gặp; thêm §7.6 (QWEN-01…08); cập nhật lỗi S2 ở §11.
  Đã chạy thật: `vlm ping` (PASS, 111 s), lỗi context 4096, lỗi kết nối, `pytest` với các biến Qwen/live. Chưa chạy:
  đường A (submodule trống), `describe`/`agent ask`/API ở chế độ `live`. §6 và §8 vẫn ở mốc 04/10.
  §4.2: thêm `uv sync --all-extras`, dùng `export`, `KNOWHOW_PG_DSN` chỉ đọc từ shell, cách tránh xung đột cổng 5432;
  mốc integration 19 pass, 0 skip.
- v1.0 (04/10/2026): bản đầu, dựa trên `main` @ `da08a2e` và hai nhánh `phuc-nguyen/agents-eval-on-main`,
  `viethoang/ingext-index-trungntresolve`.
