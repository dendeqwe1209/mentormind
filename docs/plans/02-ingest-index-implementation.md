# Implementation plan chi tiết — Ingest & Index

Bổ sung cho `02-ingest-index-plan.md` (lịch) và `02-ingest-index-spec.md` (yêu cầu). File này mô tả **code cần viết**: file, hàm, thuật toán, test, thứ tự. Mỗi bước theo CLAUDE.md: viết test từ AC trước → code tối thiểu → `make check` xanh → tick task.

> Tên module viết đầy đủ. Test đặt ở `tests/` phản chiếu `mentormind/`.

## 0. Bản đồ file
```
mentormind/
├── core/
│   ├── config.py                    # (T02-8) thêm field ingest/vector nếu chưa có
│   └── schemas/
│       ├── __init__.py
│       ├── common.py                # DataClassification            (T02-8)
│       └── document.py              # ChunkKind, DocumentChunk      (T02-1)
├── capture/ingest/
│   ├── __init__.py
│   ├── ids.py                       # doc_id, chunk_id              (T02-1)
│   ├── raw.py                       # RawBlock, RawDocument         (T02-2)
│   ├── tokens.py                    # TokenCounter                  (T02-4)
│   ├── entities.py                  # process_ids, part_numbers     (T02-4)
│   ├── chunker.py                   # RawDocument -> DocumentChunk  (T02-4)
│   ├── extractors/
│   │   ├── base.py                  # Extractor Protocol, errors    (T02-2)
│   │   ├── mmore.py                 #                               (T02-2)
│   │   ├── docling.py               #                               (T02-3)
│   │   └── surya.py                 #                               (T02-3)
│   ├── select.py                    # chọn extractor + fallback     (T02-3)
│   ├── jsonl.py                     # ghi/đọc JSONL nguyên tử       (T02-5)
│   ├── pipeline.py                  # ingest_file / ingest_path     (T02-5)
│   ├── index.py                     # JSONL -> VectorStore          (T02-6c)
│   └── cli.py                       # Typer sub-app `ingest`        (T02-5, T02-6c)
└── knowledge_base/store/
    ├── __init__.py                  # get_vector_store()            (T02-8)
    ├── vector_store.py              # VectorStore, VectorChunk...   (T02-8)
    ├── embedder.py                  # Embedder, BgeM3, FakeEmbedder (T02-6)
    ├── memory_store.py              #                               (T02-6a)
    └── pgvector_store.py            #                               (T02-6b)
tests/capture/ingest/…  tests/knowledge_base/store/…  tests/core/schemas/…
tests/fixtures/ingest/   # RawDocument mẫu (JSON), không phải file nhị phân lớn
```
Nếu Trung đã tạo sẵn `core/`, `cli.py`, `config.py`: **chỉ thêm**, không ghi đè.

## 1. Cấu hình (`core/config.py`)
Thêm các field vào `Settings` (prefix `KNOWHOW_`), nếu chưa có:

| Field | Mặc định | Dùng ở |
|---|---|---|
| `embed_model` | `BAAI/bge-m3` | embedder |
| `embed_dim` | `1024` | embedder, pgvector |
| `vector_backend` | `pgvector` | `get_vector_store` |
| `pg_dsn` | `postgresql://knowhow:change-me@localhost:5432/knowhow` | pgvector |
| `vector_table` | `knowhow_chunks` | pgvector |
| `process_id_regex` | `\b[A-Z]{3,5}\d{2}\b` | entities |
| `part_number_regex` | (chốt sau khi xem sample, xem T02-0) | entities |
| `process_id_stoplist` | `[]` | entities |
| `ingest_min_chars_per_page` | `50` | select |
| `chunk_min_tokens / chunk_max_tokens / chunk_overlap_tokens` | `300 / 800 / 50` | chunker |

Test: `test_config_defaults`, `test_config_env_override` (đặt env, gọi `get_settings.cache_clear()`).

## 2. Bước T02-8 — nền tảng tối thiểu (làm trước nếu Trung chưa xong)

**`core/schemas/common.py`**
```python
class DataClassification(StrEnum):
    PUBLIC = "public"
    SYNTHETIC = "synthetic"
    FACTORY_CONFIDENTIAL = "factory_confidential"
```
**`knowledge_base/store/vector_store.py`** — đúng như spec §5.1: `VectorChunk`, `VectorHit`, `Filters = dict[str, str | list[str]]`, `VectorStore(Protocol)`.
- `ALLOWED_FILTER_KEYS = {"kind","source_type","doc_id","data_classification","process_ids"}`; hàm `validate_filters(filters)` raise `ValueError` với khóa lạ (dùng chung cho cả 2 backend, và để chặn SQL injection ở pgvector).

**`knowledge_base/store/__init__.py`** — `get_vector_store(settings=None) -> VectorStore`: `memory` → `MemoryVectorStore(embedder)`, `pgvector` → `PgVectorStore(...)`, giá trị khác → `ValueError`.

**Tests** (`tests/knowledge_base/store/test_factory.py`): `test_ac_08_memory_backend_upsert_and_search` (spec 01 AC-08), `test_unknown_backend_raises`, `test_validate_filters_rejects_unknown_key`.

**Gửi Trung/Vinh** xác nhận interface trước khi làm tiếp T02-6.

## 3. Bước T02-1 — model `DocumentChunk`
**`core/schemas/document.py`**
```python
class ChunkKind(StrEnum):
    TEXT, TABLE, FIGURE_CAPTION, DRAWING_NOTE


class DocumentChunk(BaseModel):  # trường đúng spec 02 §3
    model_config = ConfigDict(extra="forbid")
```
Validator:
- `chunk_id` khớp `^DOC-[0-9a-f]{12}#p\d+-\d+$` và bắt đầu bằng `doc_id + "#"`.
- `text.strip()` không rỗng.
- `kind == TABLE` ⇒ dòng 2 của `text` khớp `^\|?\s*:?-{3,}` (dòng phân cách markdown).
- `process_ids`, `part_numbers`: khử trùng lặp, sắp xếp (validator `mode="after"`).

**`ingest/ids.py`**
- `doc_id_for(path) -> str`: đọc file theo khối 1 MiB, `"DOC-" + sha256.hexdigest()[:12]`.
- `make_chunk_id(doc_id, page, index) -> str`. `page` None → dùng 0.

**Tests** (`tests/core/schemas/test_document.py`, `tests/capture/ingest/test_ids.py`): `test_chunk_valid_roundtrip_json`, `test_chunk_id_pattern_rejected`, `test_table_requires_markdown_separator`, `test_empty_text_rejected`, `test_lists_deduped_sorted`, `test_extra_field_forbidden`, `test_doc_id_same_bytes_same_id`, `test_doc_id_differs_on_content`, `test_doc_id_ignores_filename`.

## 4. Bước T02-0 — spike (trước khi viết adapter, timebox nửa ngày)
Chạy thủ công, ghi kết quả vào `docs/plans/02-spike-notes.md`:
1. Cài mmore CPU. Chạy `process` trên DOC-03 và DOC-05. Ghi: cấu trúc thư mục/định dạng đầu ra, cách nó biểu diễn bảng, có số trang không, thời gian.
2. Cài Docling. Chạy trên `packing_sop_scan.pdf`. Ghi: API Python, bật OCR thế nào, bảng ra dạng gì, thời gian, dung lượng model.
3. Cài Surya. Chạy trên cùng file. Ghi: API, ngôn ngữ, thời gian.
4. Đọc mẫu để chốt `part_number_regex` mặc định.
5. Với mỗi công cụ, lưu **một** đầu ra thô nhỏ làm fixture (`tests/fixtures/ingest/mmore_sample_out/...`) — dùng để viết test adapter không cần cài công cụ.

**Điểm dừng:** nếu mmore hoặc Docling không cài/chạy được trên máy dev → dừng, báo Trung/Đạt trước khi viết adapter. Nếu Surya không được → bỏ Surya, ghi vào changelog (chấp nhận theo plan).

## 5. Bước T02-2 — adapter mmore
**`ingest/raw.py`**
```python
class RawBlock(BaseModel):
    kind: ChunkKind
    text: str                  # markdown; bảng là markdown table
    page: int | None           # None nếu nguồn không có trang
    heading: str | None = None
class RawDocument(BaseModel):
    path: str; title: str | None; num_pages: int; blocks: list[RawBlock]
    extractor: Literal["mmore","docling","surya"]
    metadata: dict[str, Any] = {}
    def chars_per_page(self) -> float   # tổng ký tự khối text / max(num_pages,1)
```
**`ingest/extractors/base.py`**
```python
class ExtractorError(Exception): ...


class Extractor(Protocol):
    name: str

    def supports(self, path: Path) -> bool: ...
    def extract(self, path: Path) -> RawDocument: ...
```
**`ingest/extractors/mmore.py`** — `MmoreExtractor`: gọi `mmore process` qua subprocess vào thư mục tạm **hoặc** Python API (chọn theo kết quả spike), parse đầu ra sang `RawDocument`. Phải:
- hỗ trợ `.pdf .docx .xlsx .pptx`;
- XLSX: mỗi sheet là một "trang" (`page = chỉ số sheet bắt đầu từ 1`), `metadata["sheet_names"]`; mỗi bảng thành một `RawBlock(kind=TABLE)`;
- lỗi subprocess/parse → `ExtractorError` kèm stderr rút gọn;
- không ghi ra ngoài thư mục tạm; xóa thư mục tạm khi xong.

**Tests** (`tests/capture/ingest/extractors/test_mmore.py`), dùng fixture đầu ra thô từ spike (không gọi mmore thật): `test_parse_mmore_output_text_blocks`, `test_parse_mmore_table_to_markdown_keeps_rows_cols`, `test_xlsx_sheet_becomes_page`, `test_subprocess_failure_raises_extractor_error`. Test gọi mmore thật đánh dấu `@pytest.mark.slow` và chạy trên `data/samples/docs/`.

**Fake** (`tests/capture/ingest/fakes.py`): `FakeExtractor(name, doc=None, raises=None)`.

## 6. Bước T02-4 — tokens, entities, chunker (làm trước T02-3 vì không phụ thuộc OCR)
**`ingest/tokens.py`**: `TokenCounter(Protocol).count(text)->int`; `BgeM3TokenCounter` (tokenizer của `KNOWHOW_EMBED_MODEL`, tải lười); `WhitespaceTokenCounter` cho test.

**`ingest/entities.py`**
- `find_process_ids(text, regex, stoplist) -> list[str]`, `find_part_numbers(text, regex) -> list[str]`; kết quả khử trùng lặp, giữ thứ tự xuất hiện rồi sắp xếp ở model.
- Regex biên dịch một lần; regex không hợp lệ → `ValueError` rõ ràng khi khởi động.

**`ingest/chunker.py`** — `chunk_document(raw, *, doc_id, classification, counter, settings) -> list[DocumentChunk]`. Thuật toán, đảm bảo xác định (không dùng thời gian/ngẫu nhiên):
1. Duyệt `raw.blocks` theo thứ tự.
2. **Khối TABLE:** xả bộ đệm text hiện có; nếu `count(table) ≤ max` → 1 chunk `TABLE`; nếu lớn hơn → tách theo hàng (giữ 2 dòng header + dòng phân cách), mỗi phần ≤ `max` token, `metadata["table_part"] = "i/n"`; một hàng tự nó > `max` → giữ nguyên hàng đó làm một phần (không cắt ngang ô).
3. **Khối TEXT/FIGURE_CAPTION/DRAWING_NOTE:** tách thành đoạn (`\n\n`); gom tham lam đến `max` token; khi xả, chunk kế tiếp bắt đầu bằng phần đuôi ~`overlap` token của chunk trước (cắt theo ranh giới câu, không cắt giữa từ). Đoạn đơn lẻ > `max` → tách theo câu, nếu vẫn quá dài thì cắt theo cửa sổ token.
4. Khối `FIGURE_CAPTION`/`DRAWING_NOTE` không gộp với TEXT (giữ `kind`); vẫn gộp với nhau cùng loại nếu ngắn.
5. `page` của chunk = trang của khối đầu tiên trong chunk; `index` đếm theo từng `page`, tăng dần.
6. Chunk cuối của một đoạn chuỗi có thể < `min` token, chấp nhận; **không** ghép qua bảng.
7. Với mỗi chunk: `process_ids/part_numbers` lấy từ `text`; `metadata` gồm `heading`, `source_path`; `title = raw.title`; `extractor = raw.extractor`.
8. Chunk rỗng sau `strip()` bị bỏ qua.

**Tests** (`tests/capture/ingest/test_chunker.py`, `test_entities.py`):
- `test_ac_10_large_table_split_with_repeated_header`
- `test_table_not_merged_with_adjacent_text`
- `test_small_table_single_chunk_all_rows`
- `test_text_chunks_within_min_max` (bằng `WhitespaceTokenCounter`)
- `test_overlap_is_about_50_tokens`
- `test_oversize_paragraph_split_by_sentence`
- `test_chunk_ids_are_sequential_per_page`
- `test_chunking_is_deterministic` (chạy 2 lần, so từng chunk)
- `test_ac_05_classification_propagates`
- `test_process_ids_regex_default`, `test_process_ids_stoplist`, `test_part_numbers_regex`, `test_invalid_regex_raises`

## 7. Bước T02-3 — Docling, Surya, chọn extractor
**`ingest/extractors/docling.py`**, **`surya.py`**: mỗi cái là `Extractor` với `name` tương ứng, import thư viện **lười** (trong hàm) để cài thiếu extra vẫn chạy được unit test; thiếu thư viện → `ExtractorError("cài extra ingest-ocr")`.

**`ingest/select.py`**
```python
def extract_with_fallback(path, extractors, *, min_chars_per_page) -> tuple[RawDocument, list[str]]:
```
Logic (spec 02 FR-02):
1. Loại tệp Office (`.docx .xlsx .pptx`): chỉ thử mmore; lỗi → `ExtractorError`, **không** rơi sang OCR.
2. PDF: thử mmore. Nếu thành công và `chars_per_page ≥ min` → trả về.
3. Nếu `< min` hoặc mmore lỗi → Docling. Nếu Docling lỗi hoặc ra 0 khối → Surya.
4. Trả thêm danh sách "lý do chuyển" (ví dụ `["mmore: 12.3 chars/page < 50", "docling: ExtractorError(...)"]`) để log FR-08.
5. Cả ba lỗi → `ExtractorError` tổng hợp mọi lý do.

**Tests** (`tests/capture/ingest/test_select.py`, dùng `FakeExtractor`): `test_text_pdf_uses_mmore`, `test_ac_03_scan_pdf_falls_back_to_docling`, `test_docling_failure_falls_back_to_surya`, `test_ac_11_all_extractors_fail_raises_with_reasons`, `test_xlsx_never_falls_back_to_ocr`, `test_zero_blocks_from_docling_counts_as_failure`, `test_chars_per_page_threshold_boundary` (49 vs 50).

## 8. Bước T02-5 — pipeline, JSONL, CLI `ingest run`
**`ingest/jsonl.py`**: `write_chunks_atomic(path, chunks)` ghi `path.tmp` rồi `os.replace`; mỗi dòng `chunk.model_dump_json()` (thứ tự khóa cố định); `read_chunks(path)` yield `(line_no, DocumentChunk)`, dòng lỗi raise `ChunkFileError(file, line_no, msg)`.

**`ingest/pipeline.py`**
```python
@dataclass class IngestResult: path, doc_id, extractor, pages, chunks, seconds, skipped: bool, error: str | None
def ingest_file(path, classification, out_dir, *, extractors, counter, settings, force=False) -> IngestResult
def ingest_path(input_, classification, out_dir, ...) -> list[IngestResult]   # thư mục hoặc 1 file
```
- Đuôi file ngoài `{.pdf,.docx,.xlsx,.pptx}` → `skipped=True`, log.
- `DataGuard.check(classification, LOCAL_PROVIDER)` gọi một lần đầu mỗi lần chạy.
- Output `out_dir/<doc_id>.jsonl`. Nếu file đã tồn tại: đọc dòng đầu, so `data_classification`; khác nhãn và không `--force` → `ClassificationMismatchError`; cùng nhãn → ghi lại (idempotent).
- Một file lỗi không dừng cả lô; kết quả lỗi được ghi vào `IngestResult.error`, mã thoát CLI ≠ 0 nếu có lỗi.
- Đo thời gian bằng `time.perf_counter()`; **không** ghi thời gian vào chunk.

**`ingest/cli.py`** (Typer, gắn vào `core/cli.py`):
```
knowhow ingest run --input PATH --classification {public|synthetic|factory_confidential}
                   --out data/work/chunks/ [--force]
```
`--classification` là `typer.Option(..., case_sensitive=False)` với `DataClassification` làm kiểu → thiếu/sai giá trị Typer tự báo lỗi, không ghi gì. Log FR-08: một dòng mỗi file `doc_id | extractor | pages | chunks | seconds` và dòng tổng.

**Tests** (`tests/capture/ingest/test_pipeline.py`, `test_cli_run.py`, dùng `CliRunner`, `FakeExtractor`):
`test_ac_04_run_twice_same_lines_and_ids`, `test_ac_05_cli_classification_written`, `test_ac_08_missing_classification_errors_no_file`, `test_ac_08_invalid_classification_errors`, `test_ac_09_reingest_other_label_errors`, `test_ac_09_force_overwrites`, `test_unsupported_extension_skipped`, `test_one_file_failure_others_continue_exit_nonzero`, `test_output_written_atomically` (mô phỏng lỗi giữa chừng, không để lại file dở), `test_jsonl_output_lines_parse_as_document_chunk`.
Test thật (`@pytest.mark.slow`): `test_ac_01_three_sample_files_produce_chunks`, `test_ac_02_xlsx_table_chunk_keeps_rows_and_cols`, `test_ac_03_scan_pdf_uses_ocr_extractor` chạy trên `data/samples/docs/`.

**Mốc DoD S1-1:** chạy lệnh trên 3 file mẫu, cả 3 cho ≥ 1 chunk, bảng XLSX đủ hàng/cột.

## 9. Bước T02-6 — embedder, memory, pgvector, `ingest index`

### 9a. Embedder và backend `memory`
**`store/embedder.py`**: `Embedder(Protocol).embed(texts) -> list[list[float]]`, `.dim`. `BgeM3Embedder` (tải model lười, batch, chuẩn hóa vector); `FakeEmbedder(dim)` sinh vector xác định từ hash của text (dùng trong test).
**`store/memory_store.py`**: `MemoryVectorStore(embedder)`:
- `upsert` theo `chunk_id` (dict), embed các chunk chưa có hoặc đã đổi `text`.
- `search`: lọc trước bằng `Filters` (bằng / thuộc tập / mảng chứa), rồi cosine; lexical BM25 đơn giản, gộp RRF (k=60). MVP: dense trước, thêm lexical sau nếu còn thời gian (Should).
- `delete(ids)` trả số bản ghi đã xóa.

Tests: `test_ac_12_filter_public_never_returns_other_classes`, `test_ac_13_filter_kind_and_process_ids_and`, `test_ac_15_upsert_twice_no_duplicates`, `test_search_respects_k`, `test_delete_removes`, `test_upsert_updates_text_and_reembeds`.

### 9b. Backend `pgvector`
**`store/pgvector_store.py`**: `PgVectorStore(dsn, table, embedder)` dùng `psycopg` + `pgvector`.
- `ensure_schema()` chạy DDL spec §5.2 (`CREATE ... IF NOT EXISTS`); nếu bảng đã có, kiểm chiều vector khớp `embedder.dim` (AC-16) — đọc từ `pg_attribute`/`format_type`.
- **Kiểm chứng `unaccent`** trong cột generated: nếu lỗi "generation expression is not immutable" → tạo hàm `knowhow_unaccent(text) IMMUTABLE` bọc `unaccent('unaccent', $1)` rồi dùng trong `tsv`. Ghi quyết định vào spec.
- `upsert`: `INSERT ... ON CONFLICT (chunk_id) DO UPDATE SET ..., updated_at = now()`, theo batch, trong một transaction.
- `search`: câu truy vấn được embed; WHERE dựng từ `Filters` **chỉ** với khóa trong `ALLOWED_FILTER_KEYS`, giá trị luôn là tham số; `process_ids` dùng toán tử `@>`/`= ANY`. Sắp xếp `embedding <=> %s`. Thêm lexical `ts_rank` + RRF sau khi phần dense đúng.
- Tên bảng lấy từ config, kiểm tra bằng regex `^[a-z_][a-z0-9_]*$` rồi mới nối vào SQL (dùng `psycopg.sql.Identifier`).

Tests (integration, `@pytest.mark.integration`, cần `make up`): `test_ac_06_filter_kind_table_returns_only_tables`, `test_ac_12_pg_filter_classification`, `test_ac_13_pg_combined_filters`, `test_ac_15_pg_upsert_idempotent_count`, `test_ac_16_dim_mismatch_raises`, `test_table_name_invalid_rejected`. Mỗi test dùng bảng riêng (tên có hậu tố ngẫu nhiên) và `DROP` khi xong.

### 9c. `ingest index`
**`ingest/index.py`**: `index_chunks(chunks_dir, store, *, batch_size=32) -> IndexResult`.
1. Với mỗi `*.jsonl` (sắp xếp tên): đọc **hết** và validate trước; có dòng lỗi → `ChunkFileError`, không ghi chunk nào của file đó (AC-14).
2. Ánh xạ: `VectorChunk(chunk_id, source_type="document", text, kind, doc_id, process_ids, data_classification, metadata={page,title,source_path,part_numbers,extractor,**chunk.metadata})`.
3. `store.upsert` theo batch. In `upserted / files_failed`.

**CLI:** `knowhow ingest index --chunks data/work/chunks/ [--batch-size 32]`; mã thoát ≠ 0 nếu có file lỗi.

Tests: `test_ac_14_bad_line_writes_nothing_for_that_file`, `test_index_maps_fields_to_vectorchunk`, `test_index_twice_same_count`, `test_index_continues_other_files_on_error` (dùng `MemoryVectorStore` + `FakeEmbedder`).

**Mốc DoD S2-5:** `ingest run` → `ingest index` trên pgvector thật; `search(filters={"data_classification": ["public"]})` và `{"kind": "table"}` trả đúng.

## 10. Thứ tự thực hiện (commit-size step, mỗi bước `make check` xanh)
| # | Việc | Phụ thuộc |
|---|---|---|
| 1 | T02-7 review data + sample_review.md + `data/samples/docs/*` | không |
| 2 | T02-0 spike | không |
| 3 | T02-8 nền tảng (nếu Trung chưa xong) | — |
| 4 | T02-1 model + ids | 3 |
| 5 | T02-4 tokens, entities, chunker | 4 |
| 6 | T02-2 raw + base + mmore | 2, 4 |
| 7 | T02-3 select + docling + surya | 6 |
| 8 | T02-5 jsonl, pipeline, CLI run → **DoD S1-1** | 5, 7 |
| 9 | T02-6a embedder + memory store | 3 |
| 10 | T02-6c ingest index (trên memory) | 8, 9 |
| 11 | T02-6b pgvector + integration | 9, `make up` |
| 12 | Chạy end-to-end trên 3 file → **DoD S2-5**; tick task, changelog | 10, 11 |

Bước 9–10 làm được **trước** khi có docker, vì chạy trên backend `memory`; chỉ bước 11 chờ Vinh.

## 11. Dependency cần thêm vào `pyproject.toml`
- extra `ingest`: `mmore` (CPU), `transformers` (tokenizer bge-m3), `sentence-transformers` hoặc `FlagEmbedding` (embed), `typer`.
- extra `ingest-ocr`: `docling`, `surya-ocr`.
- `psycopg[binary]`, `pgvector` — đề xuất thêm vào dependency lõi hoặc extra `store`; **hỏi Trung**, vì `VectorStore` dùng chung với spec 05.
- `dev`: `pytest`, `ruff`, `mypy`. Pin bản sau spike (T02-0).
- Đăng ký marker `slow`, `integration` trong cấu hình pytest.

## 12. Quy tắc chất lượng áp dụng cho mọi bước
- Type hint đầy đủ; `mypy --strict` bắt buộc cho `core/schemas`; các module còn lại theo cấu hình repo.
- Code, docstring, tên biến: tiếng Anh; thông báo hiển thị cho người dùng cuối (log/CLI): tiếng Việt.
- Mọi I/O đi qua Pydantic model; không dùng dict thô ngoài `metadata`.
- Test không gọi mạng thật; test cần model/dịch vụ nặng dùng marker.
- Không commit `data/work/`, `data/raw/`, `data/factory/`; không hardcode DSN hay khóa.
- Sau mỗi task: tick `[x]` trong `docs/02-document-ingest-ocr.md` và thêm 1 dòng Changelog.

## 13. Điểm cần hỏi trước khi code (đã gom)
1. Store tự embed hay nhận vector sẵn? (giả định: tự embed) — Trung/Vinh.
2. `psycopg`/`pgvector` vào dependency lõi hay extra riêng — Trung.
3. `knowhow_chunks` DDL có nằm trong `init.sql` hay `ensure_schema()` tạo? (giả định: cả hai, `IF NOT EXISTS`) — Vinh/dendeqwe.
4. Được commit DOC-03 vào `data/samples/docs/` không — Đạt.
