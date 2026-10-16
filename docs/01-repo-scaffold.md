# 01 — Repo Scaffold & Tooling

**Owner:** Trung (structure) · Vinh (docker-compose) · **Tasks Excel:** S0-1, S0-4, S3-1

## 1. Mục tiêu
Một khung repo mà cả 5 người code song song không giẫm chân nhau, và Claude Code sinh module mới vào đúng chỗ.

## 2. Cấu trúc thư mục (bắt buộc)
```
mentormind-knowhow-ai/
├── CLAUDE.md
├── README.md
├── Makefile
├── pyproject.toml
├── .env.example
├── .gitignore
├── .secrets/                   # CHỈ README.md: hướng dẫn lấy API key (key thật nằm trong .env)
├── docker-compose.yml
├── mentormind/                 # TOÀN BỘ mã nguồn ứng dụng — Python package `mentormind`
│   ├── __init__.py
│   ├── core/                   # dùng chung, mọi module import — Trung
│   │   ├── config/             # settings.py (Settings, pydantic-settings), secrets.py (tra key)
│   │   ├── cli.py              # Typer app gốc, gắn sub-command từng module
│   │   ├── schemas/            # Pydantic models sinh từ docs/contracts
│   │   │   ├── work_profile.py
│   │   │   ├── video.py        # VideoAsset, Segment, TranscriptSegment (spec 03 §3)
│   │   │   └── common.py       # DataClassification, Citation, ...
│   │   ├── guard/              # Constitution Điều 2
│   │   │   ├── data_guard.py   # chặn factory_confidential → cloud
│   │   │   ├── pii/            # recognizers, vault, masker, leak_guard (FR-09b)
│   │   │   ├── outbound/       # policy, session (chuỗi mask → leak → audit), audit
│   │   │   └── image/          # guard cho ảnh gửi cloud: face_blur.py (làm mờ mặt, spec 04 FR-02c)
│   │   └── providers/          # MỌI provider model: phần chung + một thư mục mỗi loại
│   │       ├── base.py, models.py, registry.py, errors.py
│   │       ├── transport/      # HttpClient, retry (spec 04 FR-07)
│   │       ├── openai_compat/  # bảng endpoint vendor, locality, resolve, chat client
│   │       ├── parsing/        # trích JSON từ câu trả lời model
│   │       ├── vlm/            # VLM (spec 04 §2): base, models, registry, factory, catalog, backends/
│   │       ├── llm/            # LLM (spec 06 §2): base, models, registry, factory, catalog, context, backends/
│   │       ├── asr/            # ASR (spec 03 FR-07c): faster_whisper tại máy, remote trên máy chủ suy luận
│   │       └── inference/      # máy chủ suy luận của đội (Whisper, Docling, bge-m3): endpoint, client
│   ├── capture/                # Việt Hoàng
│   │   ├── ingest/             # spec 02
│   │   └── video/              # spec 03
│   ├── processing/             # Phúc
│   │   └── vlm/                # spec 04
│   ├── knowledge_base/
│   │   ├── kg/                 # spec 05 — Trung
│   │   ├── retrieval/          # spec 05 — Trung
│   │   ├── sigma/              # spec 07 — Vinh
│   │   └── store/              # Vinh
│   │       ├── profile_store.py    # lưu WorkProfile (SQLite)
│   │       └── vector_store.py     # VectorStore: pgvector | memory (FR-05c)
│   ├── agents/                 # spec 06 — Phúc
│   ├── evaluation/             # spec 09 — Phúc
│   ├── backend/app/            # spec 08 — FastAPI, `mentormind.backend.app.main:app` — Vinh
│   ├── ui/streamlit_app.py     # spec 08 — Vinh
│   └── frontend/               # UI tablet tại trạm (Vite/React, không phải Python)
├── tests/                      # pytest, phản chiếu mentormind/: tests/<module>/.../test_*.py
├── infra/
│   ├── postgres/init.sql       # CREATE EXTENSION vector, unaccent
│   └── docker/                 # Dockerfile môi trường chạy
├── docs/                       # spec-driven: nguồn sự thật
│   └── contracts/              # JSON Schema — thắng mọi mô tả văn xuôi
├── data/                       # KHÔNG phải code
│   ├── samples/                # dữ liệu public/synthetic nhỏ, được commit
│   ├── mock_sigma/             # CSV mock, được commit
│   ├── golden_set/             # spec 09, được commit
│   └── work/                   # output trung gian, KHÔNG commit
├── scripts/demo.sh
└── 3rdparty/vlm_server/        # submodule mentormind-inference (trước: vlm-engine): VLM (Ollama Q4 / vLLM BF16) + gateway CPU (ASR, embeddings, Docling)
```

> **Quy ước tên module trong các spec:** mọi đường dẫn module viết tắt, bỏ tiền tố package gốc — `core.schemas` nghĩa là `mentormind.core.schemas`, `core.providers.vlm` là `mentormind.core.providers.vlm`; đường dẫn file `core/guard/data_guard.py` là `mentormind/core/guard/data_guard.py`. Tên CLI (`knowhow`) và prefix biến môi trường (`KNOWHOW_`) không đổi.

## 3. Functional Requirements
- **FR-01** `pyproject.toml` ở gốc repo dùng `uv`, Python `>=3.11,<3.13`. Mã nguồn nằm trong **một package gốc `mentormind/`** (tách khỏi `tests/`, `infra/`, `docs/`, `data/`); các module `core`, `capture`, `processing`, `knowledge_base`, `agents`, `evaluation`, `backend` là sub-package của nó, import dạng `mentormind.core...`. Build config chỉ đóng gói `mentormind` (trừ `mentormind/frontend`). Entry point `knowhow = "mentormind.core.cli:app"`. `.python-version` ghim `3.11` để venv dev/CI khớp `mypy python_version` (uv.lock chọn numpy khác nhau cho 3.11 và ≥ 3.12). `backend/` không có `requirements.txt` riêng — dependency của API nằm trong extra `api`.
- **FR-02** Dependency nhóm theo extra: `ingest`, `video`, `vlm`, `kg`, `api`, `ui`, `eval`, `dev`. `uv sync --all-extras` cài đủ.
- **FR-03** `config.py` định nghĩa `Settings` đọc từ env với prefix `KNOWHOW_`; mọi module lấy config qua `get_settings()` (cache).
- **FR-04** `Makefile` có target: `up`, `down`, `check` (ruff check + ruff format --check + mypy + `mypy --strict mentormind/core/schemas mentormind/core/guard` + pytest), `test`, `demo`, `fmt`; server VLM tự host: `vlm-server-sync`, `vlm-server`, `vlm-server-smoke` (spec 04 FR-08).
- **FR-05** `docker-compose.yml`: `neo4j:5` (APOC bật, port 7474/7687, volume) và `pgvector/pgvector:pg16` (port 5432, volume, init script `infra/postgres/init.sql` chạy `CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS unaccent;`, rồi dựng schema: `knowledge_units` = một `WorkProfile` theo contract (cột trùng tên field, ràng buộc `allOf` của contract thành `CHECK`), nhãn `data_classification` đúng constitution Điều 2 (domain, mặc định `factory_confidential`), bảng vector duy nhất `knowhow_chunks` (FR-05c), full-text cấu hình `mm_unaccent` = `simple` + `unaccent`), cả hai trong **profile `lite`**. Healthcheck cho neo4j (`cypher-shell`) và postgres (`pg_isready`). Mọi port chỉ publish trên `127.0.0.1`.
- **FR-05d** Hai container dev chạy không cần profile (`docker compose up -d`): `mentormind` (image `infra/docker/mentormind.Dockerfile`: Python 3.11 + uv + ffmpeg + mọi extra; repo bind-mount tại `/workspace`, venv ở `/opt/venv`) và `vlm-server` (image của submodule `vlm-engine`, đúng 1 GPU `VLM_GPU`). Code trong `mentormind` chỉ gọi API VLM qua `KNOWHOW_VLM_BASE_URL=http://vlm-server:8100/v1`. `VLM_SERVER_AUTOSTART=true` → server Qwen3-VL bật cùng container; `false` (mặc định) → container chờ, bật bằng `docker compose exec vlm-server python -m vlm_server serve`. Override đặt trong `infra/docker/`: `docker-compose.cdi.yml` (GPU qua CDI), `docker-compose.devbox.yml` (rootless Docker: host network), `docker-compose.rocm.yml` (AMD, vd. MI250); chọn bằng `make up PLATFORM=rocm|devbox|cdi`.
- **FR-05b** Giới hạn tài nguyên để chạy được trên máy dev: Neo4j đặt `NEO4J_server_memory_heap_max__size=1G`, `NEO4J_server_memory_pagecache_size=512M`; mọi service trong compose có `mem_limit` (neo4j 2g, postgres 1g, mentormind 1g; vlm-server `VLM_SERVER_MEM_LIMIT`, mặc định 32g vì vLLM map checkpoint 17 GB vào RAM host khi nạp).
- **FR-05c** Vector store đứng sau interface `knowledge_base.store.vector_store.VectorStore` (`upsert(chunks)`, `search(query, k, filters) -> list[VectorHit]`, `delete(ids)`). Hai implementation chọn bằng `KNOWHOW_VECTOR_BACKEND`: `pgvector` (mặc định, cần `make up`) và `memory` (in-process, cosine + BM25 đơn giản, dùng cho unit test/CI không docker) — chỉ đổi config, Constitution Điều 5. Dòng dữ liệu là `core.schemas.vector.VectorChunk` (`chunk_id`, `source_type`, `ref_id`, `text`, `kind`, `process_ids`, `part_numbers`, `data_classification`, `metadata`, `embedding?`) — cột y hệt bảng `knowhow_chunks`; kết quả `VectorHit(chunk, score)`. Store nhận một `Embedder` (`dim`, `embed(texts)`); mặc định `HashingEmbedder` (feature hashing, không model/mạng) cho test/offline, bge-m3 đến ở spec 02. Backend `memory`: cosine + BM25 trên token bỏ dấu, gộp RRF k=60 (như spec 05). Filter: `source_type`, `kind`, `ref_id`, `data_classification` (khớp đúng), `process_id`, `part_number` (chunk có chứa). Backend `pgvector` làm ở spec 02 T02-6; trước đó `get_vector_store()` báo lỗi rõ ràng.
- **FR-06** `.gitignore` chặn: `data/raw/`, `data/factory/`, `data/work/`, `.env` (**trừ** `.env.example`), `.secrets/*` (**trừ** `.secrets/README.md`), `guidance/`, `*.mp4|*.mov|*.mkv|*.webm|*.avi|*.wav|*.mp3` **trừ** `data/samples/**` và `data/video/*` (video demo public, đi qua **Git LFS** theo `.gitattributes`).
- **FR-07** GitHub Actions `ci.yml`: trên push/PR chạy `uv sync --all-extras --locked` + `make check` (Python theo `.python-version`, không tải LFS, không cần submodule). Test không cần docker (dùng fake).
- **FR-08** `core/schemas/work_profile.py` là Pydantic v2 model tương đương 1-1 với `docs/contracts/work_profile.schema.json`, kèm hàm `validate_against_contract(obj) -> None` dùng `jsonschema` để kiểm tra chéo.
- **FR-09** `core/guard/data_guard.py`: `DataGuard.check(classification, provider)` raise `ConfidentialDataError` khi `classification == factory_confidential` và `provider.is_cloud`.
- **FR-09b** Dữ liệu **được phép** ra cloud vẫn phải che dữ liệu nhạy cảm trước khi gửi — áp dụng thiết kế masking của `bankassist-mcp` (Trung): `core/guard/pii/` — recognizer văn bản tự do theo thứ tự thẻ (Luhn) → email → di động VN → CCCD 12 số → CMND 9 số (chỉ khi có từ khóa CMND/CMT gần đó, để số tiền không bị che), cộng giá trị đã biết (tên chuyên gia...) và mẫu riêng của nhà máy (`KNOWHOW_GUARD_EXTRA_PATTERNS`); token `[TYPE_n]` ổn định trong một phiên, hoàn nguyên được (`PiiVault`); `LeakGuard` quét lần cuối và **từ chối** gửi nếu còn sót — không tắt được; `core/guard/outbound/` ghép chuỗi DataGuard → mask → LeakGuard → audit (JSONL, chỉ số đếm, không giá trị). Provider tự host không bị che (dữ liệu không rời nhà máy).

## 4. Biến môi trường (`.env.example`)
```
KNOWHOW_NEO4J_URI=bolt://localhost:7687
KNOWHOW_NEO4J_USER=neo4j
KNOWHOW_NEO4J_PASSWORD=change-me
KNOWHOW_VECTOR_BACKEND=pgvector        # pgvector | memory
KNOWHOW_PG_DSN=postgresql://knowhow:change-me@localhost:5432/knowhow
KNOWHOW_VECTOR_TABLE=knowhow_chunks
KNOWHOW_EMBED_DIM=1024                 # bge-m3 dense
KNOWHOW_EMBEDDER=bge-m3                # bge-m3 (tại máy) | remote (máy chủ suy luận) | hashing (dev)
KNOWHOW_DOC_EXTRACTOR=docling          # docling (tại máy) | remote (máy chủ suy luận)
KNOWHOW_ASR_PROVIDER=faster_whisper    # faster_whisper (tại máy) | remote (máy chủ suy luận) | fake
# máy chủ suy luận riêng của đội cho các giá trị `remote` (spec 02 FR-02c/FR-07d, spec 03 FR-07c);
# local/cloud theo URL + KNOWHOW_LOCAL_HOSTS như VLM; key trống = KNOWHOW_VLM_API_KEY khi KNOWHOW_VLM_BASE_URL cùng host
KNOWHOW_INFERENCE_URL=
KNOWHOW_INFERENCE_API_KEY=
KNOWHOW_INFERENCE_TIMEOUT_S=1800
KNOWHOW_INFERENCE_MAX_RETRIES=2
KNOWHOW_VLM_PROVIDER=local_openai      # local_openai | openrouter | siliconflow | qwen_api | openai_compatible | fake
# trống = endpoint mặc định của provider (local_openai: Ollama http://127.0.0.1:11434/v1, qwen3-vl:8b) và tên Qwen3-VL-8B của provider đó
KNOWHOW_VLM_BASE_URL=
KNOWHOW_VLM_MODEL=
KNOWHOW_VLM_FPS=4
KNOWHOW_VLM_MAX_FRAMES=48
KNOWHOW_VLM_TIMEOUT_S=90
KNOWHOW_VLM_MAX_RETRIES=3
KNOWHOW_VLM_JSON_MODE=auto             # auto | json_schema | json_object | off
KNOWHOW_VLM_MAX_TOKENS=2048
KNOWHOW_VLM_EXTRA_BODY={"presence_penalty": 1.5}
KNOWHOW_GUARD_MASK_TEXT=true           # che PII trong text gửi provider cloud (LeakGuard luôn chạy)
KNOWHOW_GUARD_BLUR_FACES=true          # làm mờ mặt trong khung hình gửi provider cloud
KNOWHOW_GUARD_EXTRA_PATTERNS={}        # mã riêng của nhà máy cần che, vd. {"EQUIPMENT": "SIGMA-EQ-\\d+"}
KNOWHOW_LLM_PROVIDER=qwen_api
KNOWHOW_LLM_MODEL=qwen-plus
KNOWHOW_EMBED_MODEL=BAAI/bge-m3
KNOWHOW_PROFILE_DB=data/work/profiles.sqlite
KNOWHOW_SIGMA_ADAPTER=csv
KNOWHOW_SIGMA_CSV_DIR=data/mock_sigma
```
> Tên model/URL cloud là giá trị mặc định cho giai đoạn demo; kiểm tra lại tên model hiện hành của nhà cung cấp trước khi chạy.
> API key nằm **cùng trong `.env`**: key theo vendor (`OPENROUTER_API_KEY`, `SILICONFLOW_API_KEY`, `DASHSCOPE_API_KEY`, `VLM_SERVER_API_KEY`) đặt thẳng vào `.env` (cách lấy key: `.secrets/README.md`); `KNOWHOW_VLM_API_KEY` chỉ dùng để ép một key. Trong file dotenv, không đặt comment cùng dòng với giá trị rỗng (dotenv đọc comment thành giá trị).

## 5. Acceptance Criteria
- **AC-01** Clone mới → `uv sync --all-extras && make check` pass, không cần mạng tới dịch vụ ngoài.
- **AC-02** `make up` → trong 120s, healthcheck Neo4j và Postgres đều healthy; `SELECT extname FROM pg_extension` có `vector` và `unaccent`.
- **AC-03** `uv run knowhow --help` liệt kê sub-command: `ingest`, `video`, `vlm`, `kg`, `agent`, `sigma`, `eval`.
- **AC-04** Một WorkProfile mẫu hợp lệ pass cả Pydantic lẫn `validate_against_contract`; một profile VLM `draft` có `reason` khác null bị cả hai từ chối.
- **AC-05** `DataGuard.check("factory_confidential", cloud_provider)` raise; với `local_provider` không raise.
- **AC-06** `git add data/raw/x.mp4` bị `.gitignore` bỏ qua; `data/samples/demo.mp4` thì không; `.env` (chứa mọi key) bị bỏ qua, `.env.example` và `.secrets/README.md` thì không.
- **AC-07** `docker compose config` cho thấy mọi service có `mem_limit`; tổng của stack demo lite (`mentormind` + `postgres` + `neo4j`) ≤ 4 GB. `vlm-server` (Ollama trên GPU, tùy chọn — có thể thay bằng provider cloud) có giới hạn riêng.
- **AC-08** `Settings` với `KNOWHOW_VECTOR_BACKEND=memory` → `get_vector_store()` trả store dùng được (upsert + search) mà không cần docker.
- **AC-09** Masking văn bản khớp bộ ca của bankassist-mcp: SĐT (`0…`, `+84…`, có dấu cách) → cùng một `[PHONE_n]`; CCCD, email, thẻ hợp lệ Luhn bị che; số tiền `500000000`, ngày `15082026`, mã 16 số sai Luhn giữ nguyên; tên đã biết bị che không phân biệt hoa thường; hoàn nguyên trả đúng chuỗi gốc; vault cô lập theo phiên.
- **AC-10** LeakGuard phát hiện SĐT/CCCD/email còn sót; tắt masking mà text còn PII → vẫn bị chặn và audit ghi `SecurityAlert` không kèm giá trị.
- **AC-11** Audit của lời gọi cloud ghi số lượng đã che theo loại, không chứa giá trị gốc; lời gọi tự host không bị che và không ghi audit.

## 6. Tasks
- [x] T01-1 Tạo `pyproject.toml`, `Makefile`, `.gitignore`, `.env.example`, `CLAUDE.md`, `README.md`.
- [x] T01-2 `core/config/`, `core/cli.py` với sub-command rỗng cho từng module.
- [x] T01-3 `core/schemas/` + `validate_against_contract` + test AC-04.
- [x] T01-4 `core/guard/data_guard.py` + test AC-05.
- [x] T01-5 `docker-compose.yml` + healthcheck + giới hạn bộ nhớ (AC-02, AC-07) — làm theo task D3 (Phúc). Đo 28/9 trên máy dev: `postgres` + `neo4j` healthy sau 33 s, có extension `vector`/`unaccent`, APOC 5.26; RAM thực ~1 GB (neo4j 970 MiB, postgres 32 MiB); `mentormind` → `vlm-server` (1 GPU, autostart) → `knowhow vlm ping --frames 48` PASS.
- [x] T01-7 Interface `VectorStore` + backend `memory` + factory `get_vector_store()` theo config (AC-08).
- [x] T01-6 CI workflow.

## Changelog
- v1.0 (23/9): khởi tạo.
- v1.1 (24/9): FR-05b giới hạn bộ nhớ Neo4j/Milvus; FR-05c Milvus Lite cho dev/CI; thêm `KNOWHOW_VLM_MAX_FRAMES` (AC-07, AC-08, T01-7).
- v1.2 (27/9): đổi Milvus → PostgreSQL 16 + pgvector (FR-05, FR-05b, env); FR-05c thay Milvus Lite bằng interface `VectorStore` + backend `memory`; AC-02, AC-07 (≤ 4 GB), AC-08, T01-7 cập nhật theo.
- v1.3 (27/9): bỏ `src/knowhow/`, dùng layout theo architecture §6 (`core/`, `capture/`, `processing/`, `knowledge_base/`, `agents/`, `evaluation/`, `backend/app/`); `specs/` → `docs/`; entry point `core.cli:app` (FR-01, FR-05c, FR-08, FR-09).
- v1.4 (28/9, Phúc): tách code khỏi test/hạ tầng/tài liệu — toàn bộ mã nguồn vào package gốc `mentormind/` (gồm `backend/`, `frontend/`), `tests/`, `infra/`, `docs/`, `data/` ở gốc; spec giữ tên module viết tắt (bỏ tiền tố `mentormind.`); entry point `mentormind.core.cli:app` (§2, FR-01).
- v1.5 (28/9, Phúc): T01-1..T01-4 xong; cây thư mục chi tiết `core/{config,guard/{pii,outbound},providers/{transport,openai_compat,parsing}}`, `.secrets/`, submodule `3rdparty/vlm_server` (vlm-engine); FR-04 thêm `vlm-server*` + `mypy --strict`; FR-06 + AC-06 chặn `.secrets/*`, `guidance/`, `*.mkv|*.webm|*.avi`; env VLM mặc định `local_openai` + nhóm `KNOWHOW_GUARD_*`; FR-09b masking PII ra cloud (port bankassist-mcp) + AC-09..AC-11 (spec 04 v1.4–v1.5). `extras` chỉ khai báo dependency của task đã làm (`vlm`, `api`, `dev`).
- v1.6 (28/9, Phúc): T01-5 xong theo task D3 — profile `lite` (pgvector + Neo4j giới hạn bộ nhớ), FR-05d hai container dev `mentormind` + `vlm-server` với `VLM_SERVER_AUTOSTART`, override CDI/devbox/ROCm; AC-07 tính 4 GB cho stack demo lite (không gồm vlm-server GPU); Makefile `up`/`down`/`dev-up`/`dev-shell`.
- v1.7 (28/9, Phúc): override compose chuyển vào `infra/docker/`, chọn bằng `make up PLATFORM=rocm|devbox|cdi` (FR-05d); override ROCm thêm GID `render` của host.
- v1.8 (28/9, Phúc): API key nằm cùng trong `.env` (§4), `.secrets/` chỉ còn `README.md` hướng dẫn lấy key (FR-06, AC-06).
- v1.9 (28/9, Phúc): FR-06 cho phép `data/video/*` (video demo public LASI) vào git qua **Git LFS** (`.gitattributes`); dữ liệu nhà máy vẫn bị chặn.
- v1.10 (28/9, Phúc): contract WorkProfile thêm `actor` (`human` | `robot` | `machine` | `null`: ai làm bước; `human` gộp công nhân + kỹ sư), `schema_version` giữ `1.0` (FR-08; spec 04 AC-18).
- v1.11 (28/9, Phúc): mọi provider model về `core/providers/` (`vlm/`, `llm/` cạnh phần dùng chung); làm mờ mặt ở `core/guard/image.py` (§2).
- v1.12 (29/9, review): `init.sql` v1.2 khớp contract + constitution — nhãn `public|synthetic|factory_confidential`, `reason_source` chỉ `expert_verbal|expert_interview`, `knowledge_units` = WorkProfile (có `data_classification`, thời gian evidence tính bằng giây), CHECK cho 3 luật `allOf` + reject phải có comment, một bảng vector `knowhow_chunks` (trigger: chỉ profile approved, bỏ duyệt thì xóa chunk), full-text `simple`+`unaccent`; đã chạy thử trên `pgvector/pgvector:pg16` (FR-05). T01-7 xong: `VectorChunk`/`VectorHit`, `Embedder`, backend `memory`, `get_vector_store()` (FR-05c, AC-08). T01-6 xong: `.github/workflows/ci.yml` (FR-07). `.python-version` = 3.11 (FR-01). API đọc `core.config.Settings` (`app_name`, `cors_origins`); bỏ `backend/requirements.txt`, `backend/app/config.py`, `backend/.env.example` (FR-01, FR-03). `scripts/demo.sh`: preflight + luồng spec 08 §4.
- v1.13 (08/10, Phúc): §4 thêm `KNOWHOW_INFERENCE_URL`/`_API_KEY`/`_TIMEOUT_S`/`_MAX_RETRIES` (máy chủ suy luận riêng của đội cho Whisper, Docling, bge-m3), `KNOWHOW_DOC_EXTRACTOR`, giá trị `remote` của `KNOWHOW_EMBEDDER` và `KNOWHOW_ASR_PROVIDER`; §2 thêm `core/providers/{asr,inference}/` (spec 02 v1.5, spec 03 v1.9).
- v1.14 (08/10, Phúc, review): §4 `KNOWHOW_INFERENCE_API_KEY` trống chỉ lấy `KNOWHOW_VLM_API_KEY` khi `KNOWHOW_VLM_BASE_URL` cùng host (spec 02 v1.6).
- v1.15 (08/10, Phúc): submodule `3rdparty/vlm_server` đổi sang repo mentormind-inference (URL https, repo public) — gateway CPU cho ASR/embeddings/Docling từ xa (spec 02/03, `KNOWHOW_INFERENCE_URL`).
