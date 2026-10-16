# 02 — Document Ingest & OCR

**Owner:** Việt Hoàng · **Tasks Excel:** S0-5, S1-1, S2-5

## 1. Mục tiêu
Biến bản vẽ kỹ thuật, SOP cũ, file Excel/Word thành các `DocumentChunk` có cấu trúc, rồi index vào PostgreSQL/pgvector để retriever (spec 05) dùng được.

## 2. Công cụ
| Việc | Công cụ | Ghi chú |
|---|---|---|
| PDF/DOCX/XLSX/PPTX (kể cả bản scan, vùng ảnh có chú thích) | Docling (OCR bật) | đường chính (v1.4, spike T02-0; chờ Trung duyệt); chạy tại máy hoặc trên máy chủ suy luận của đội (`KNOWHOW_DOC_EXTRACTOR=remote`, FR-02c) |
| PDF khi Docling lỗi | mmore `process` chế độ fast | fallback, chỉ text, `metadata.degraded = true` |
| Surya đứng riêng | — | bỏ; đã nằm trong `mmore[process]` nếu sau này cần |
| Embed | bge-m3 (`KNOWHOW_EMBED_MODEL`) | dense 1024 chiều; tại máy hoặc trên máy chủ suy luận (`KNOWHOW_EMBEDDER=remote`, FR-07d) |
| Index vào pgvector | `knowledge_base.store.vector_store` (spec 01 FR-05c) | hybrid dense + full-text |

Extract/OCR và embed chạy trên máy này hoặc trên **máy chủ suy luận riêng của đội** (`KNOWHOW_INFERENCE_URL`, thường là máy tự host VLM; cùng máy chủ chạy Whisper của spec 03 FR-07c). Không bao giờ gọi API OCR/embedding của bên thứ ba. Máy chủ là local hay cloud xét theo URL như VLM (spec 04 AC-23): địa chỉ private/LAN/Tailscale hoặc host khai báo trong `KNOWHOW_LOCAL_HOSTS` là local; host public khác là cloud, và `DataGuard` chặn dữ liệu `factory_confidential` **trước khi** gửi bất cứ gì. Xác thực: `Authorization: Bearer <KNOWHOW_INFERENCE_API_KEY>` (trống → `KNOWHOW_VLM_API_KEY`, nhưng chỉ khi `KNOWHOW_VLM_BASE_URL` cùng host với `KNOWHOW_INFERENCE_URL` — máy tự host VLM cũng chạy suy luận; key ép cho vendor cloud không bao giờ đi tới máy chủ khác; không có key → không gửi header), hoặc basic auth trong URL; timeout `KNOWHOW_INFERENCE_TIMEOUT_S` (mặc định 1800 s; riêng bước kết nối tối đa 10 s), thử lại `KNOWHOW_INFERENCE_MAX_RETRIES` (mặc định 2) khi lỗi kết nối, 429 hoặc 5xx. Tệp tải lên (Docling, Whisper của spec 03) đã gửi mà hết giờ chờ trả lời (hoặc proxy trả 504) thì **không gửi lại**: máy chủ vẫn đang xử lý tệp đó, bản gửi lại chỉ xếp hàng sau nó.

## 3. Data model — `core.schemas.document.DocumentChunk`
```python
class ChunkKind(StrEnum):
    TEXT = "text"
    TABLE = "table"
    FIGURE_CAPTION = "figure_caption"
    DRAWING_NOTE = "drawing_note"


class DocumentChunk(BaseModel):
    chunk_id: str  # f"{doc_id}#p{page}-{index}"
    source_type: Literal["document"] = (
        "document"  # khớp Citation.source_type (spec 05), dùng làm cột filter trong bảng vector
    )
    doc_id: str  # "DOC-" + sha256(file bytes)[:12]
    source_path: str
    title: str | None
    page: int | None
    kind: ChunkKind
    text: str  # markdown; bảng giữ dạng markdown table
    process_ids: list[str] = []  # công đoạn liên quan nếu nhận ra (VD "PACK01")
    part_numbers: list[str] = []
    data_classification: DataClassification
    extractor: Literal["mmore", "docling", "surya"]
    metadata: dict[str, Any] = {}
```

## 4. Functional Requirements
- **FR-01** `knowhow ingest run --input <dir|file> --classification <public|synthetic|factory_confidential> --out data/work/chunks/` xử lý mọi file hỗ trợ (`.pdf .docx .xlsx .pptx`; định dạng khác bị bỏ qua và log `skipped`), ghi một JSONL `<doc_id>.jsonl` cho mỗi file nguồn, mỗi dòng một `DocumentChunk`, ghi qua file tạm rồi rename.
- **FR-01b** `--classification` bắt buộc, không có mặc định; thiếu hoặc ngoài enum → lỗi, không ghi file. Chạy lại cùng file với nhãn khác là lỗi trừ khi có `--force`. Một file lỗi không dừng cả lô (exit code 1 cuối lô). Gọi `DataGuard.check` một lần mỗi lượt, trước khi đọc file nào: với máy này, hoặc với extractor đầu tiên gửi file đi (FR-02c) nếu có — URL cloud + `factory_confidential` → `ConfidentialDataError`, không ghi file, không upload.
- **FR-02** Extractor chính là Docling cho `.pdf .docx .xlsx .pptx` (OCR bật cho vùng ảnh, mỗi bảng ra markdown table, mỗi khối mang số trang/sheet). Nếu Docling lỗi hoặc ra 0 khối: với PDF chuyển sang mmore fast (chỉ text; `metadata.degraded = true`); với file Office báo lỗi. Log lý do chuyển (FR-08). Chữ OCR được bên trong hình/bản vẽ trở thành chunk `kind=drawing_note` (theo trang). *(Đánh giá extractor theo từng trang — đề xuất 1 — không còn cần với đường Docling.)*
- **FR-02c** `KNOWHOW_DOC_EXTRACTOR=remote` (mặc định `docling` = chạy tại máy): Docling chạy trên máy chủ suy luận — `POST {KNOWHOW_INFERENCE_URL}/documents/convert` (multipart `file`) trả `{"filename", "num_pages", "document": DoclingDocument.export_to_dict()}`; client dựng lại `DoclingDocument` bằng `docling_core` (thiếu → lỗi nêu cách cài) rồi map bằng cùng hàm của FR-02, nên chunk giống hệt chạy local (`extractor = docling`). Máy chủ lỗi (vd. 422 `{"error"}`) tính như Docling lỗi: PDF rơi xuống mmore fast (FR-02), log ghi `docling-remote`. Thiếu `KNOWHOW_INFERENCE_URL` → lỗi nêu tên biến.
- **FR-02b** Mỗi trang có tỉ lệ chữ IPA-mở-rộng/Hy Lạp trên tổng chữ cái > `KNOWHOW_TEXT_QUALITY_MAX_ODD_RATIO` (mặc định 0,05, tối thiểu 20 chữ cái) bị coi là text layer nghi sai mã hóa. Chỉ **cảnh báo**: trang vẫn được chunk, dòng log FR-08 nêu số trang cần xem tay; không tự OCR lại (khác đề xuất 2 gốc, chờ Trung duyệt).
- **FR-03** Bảng được giữ nguyên cấu trúc dạng markdown table, mỗi bảng là 1 chunk `kind=table`. Bảng > 800 token được tách theo hàng, lặp header ở mỗi phần, `metadata.table_part = "i/n"`, vẫn `kind=table`.
- **FR-04** Chunk văn bản: 300–800 token, không cắt ngang bảng, overlap 50 token.
- **FR-05** Nhận diện `process_ids` bằng regex cấu hình được (`KNOWHOW_PROCESS_ID_REGEX`, mặc định `\b[A-Z]{3,5}\d{2}\b`, loại bớt qua `KNOWHOW_PROCESS_ID_STOPLIST` cho các chuỗi như `ISO27`, `REV01`) và `part_numbers` bằng `KNOWHOW_PART_NUMBER_REGEX` (mặc định `\b[A-Z]{2}\d{6}-\d{4}\b`).
- **FR-06** Idempotent: cùng file (cùng hash) chạy lại → cùng `doc_id`, cùng `chunk_id`, không nhân đôi.
- **FR-07** `knowhow ingest index --chunks data/work/chunks/` embed chunk và upsert vào bảng `KNOWHOW_VECTOR_TABLE` qua `VectorStore` (không dùng mmore index — mmore index chỉ hỗ trợ Milvus). Metadata (`source_type="document"`, `doc_id`, `kind`, `process_ids`, `data_classification`) lưu thành cột filter được. Bảng dùng chung với chunk `work_profile` của spec 05, phân biệt bằng `source_type`; upsert theo `chunk_id` nên chạy lại không nhân đôi.
- **FR-07b** Store tự embed văn bản khi `upsert` và câu truy vấn khi `search` (embedder mặc định bge-m3, `KNOWHOW_EMBEDDER=hashing` chỉ cho dev). `Filters` là dict: `{"kind": "table"}` (bằng), `{"data_classification": ["public","synthetic"]}` (thuộc tập), `{"process_ids": "PACK01"}` (mảng chứa giá trị); nhiều khóa = AND. `ingest index` validate cả file JSONL trước khi ghi; `KNOWHOW_EMBED_DIM` lệch cột `vector(N)` → lỗi khi khởi động. Bảng `knowhow_chunks` định nghĩa trong `infra/postgres/init.sql`.
- **FR-07d** `KNOWHOW_EMBEDDER=remote`: cùng bge-m3 trên máy chủ suy luận — `POST {KNOWHOW_INFERENCE_URL}/embeddings` JSON `{"model": KNOWHOW_EMBED_MODEL, "input": [...]}`, tối đa 32 đoạn mỗi request → `data[i].embedding` xếp lại theo `index`, số chiều phải bằng `KNOWHOW_EMBED_DIM`, chuẩn hoá L2. Khi `upsert`, store báo cho embedder nhãn chặt nhất của các chunk cần embed: URL cloud + `factory_confidential` → `ConfidentialDataError` trước khi gửi (`ingest index`: chỉ file đó lỗi, file khác vẫn index). Văn bản không có nhãn — câu truy vấn của `search`, câu hỏi của agent (spec 06) và của đánh giá (spec 09) — coi là `factory_confidential` như router của spec 05, nên embedder `remote` ở URL cloud không tìm kiếm được: khai báo host trong `KNOWHOW_LOCAL_HOSTS`. Agent dùng embedder của vector store; store không có thì dùng embedder theo `KNOWHOW_EMBEDDER`.
  Phạm vi: chế độ `remote` dành cho **máy chủ suy luận của đội** (máy riêng của nhóm, khai báo host trong `KNOWHOW_LOCAL_HOSTS` nếu đi qua URL public như ngrok) — dùng khi demo; triển khai thực tế chạy local. Không làm chuỗi che dữ liệu/LeakGuard/audit của spec 01 FR-09b cho URL cloud: file audio/tài liệu không che được, và URL cloud không phải cách dùng dự kiến — ở URL cloud chỉ còn DataGuard (chặn `factory_confidential`).
- **FR-07c** `ingest index --replace-doc <doc_id>` (lặp lại được) xóa chunk của `doc_id` cũ **sau khi** index xong, vì file nguồn đổi thì `doc_id` đổi và chunk cũ sẽ còn tìm thấy được. Không xóa nếu có file lỗi, và không bao giờ xóa `doc_id` vừa index trong cùng lần chạy. `VectorStore.delete_where(filters)` từ chối filter rỗng.
- **FR-08** Log một dòng tóm tắt mỗi file: extractor dùng, số trang, số chunk, thời gian.

## 5. Acceptance Criteria
- **AC-01** 3 file mẫu trong `data/samples/docs/` (1 PDF text, 1 PDF scan bản vẽ, 1 XLSX) → tất cả ra chunk, không file nào 0 chunk.
- **AC-02** Bảng trong XLSX mẫu → chunk `kind=table` giữ đủ số hàng/cột.
- **AC-03** Trang ảnh/scan → `extractor = docling` và có text từ OCR. Bộ kiểm: `6-7 NASWEB Supplier-Label-Tech Spec.pdf` (trang 3, 6) và `packing_sop_scan.pdf` (scan giả, `synthetic`). *(Đề xuất 4, chờ duyệt.)*
- **AC-04** Chạy `ingest run` 2 lần → số dòng JSONL không đổi, `chunk_id` trùng khớp.
- **AC-05** Chunk mang đúng `data_classification` được truyền vào CLI.
- **AC-06** Sau `ingest index`, `VectorStore.search` với filter `kind = "table"` trả về đúng các chunk bảng. (test integration, đánh dấu `@pytest.mark.integration`, chỉ chạy khi `make up`)
- **AC-07** (S0-5) `docs/data/sample_review.md` có 1 dòng cho mỗi file sample, đủ cột (text layer, ngôn ngữ, chất lượng scan, số bảng, nhãn), kết luận ACCEPT/REDO; mỗi REDO có hành động cụ thể.
- **AC-08** `ingest run` thiếu `--classification` hoặc giá trị ngoài enum → lỗi, không ghi file.
- **AC-09** Chạy lại cùng file với `--classification` khác → lỗi; với `--force` → ghi đè.
- **AC-10** Bảng lớn hơn 800 token → nhiều chunk `kind=table`, mỗi chunk lặp header và có `metadata.table_part`.
- **AC-11** Extractor lỗi → chuyển extractor tiếp theo; mọi extractor lỗi → file báo lỗi kèm mọi lý do, các file khác vẫn xử lý.
- **AC-12** `search` với `filters={"data_classification": ["public"]}` không bao giờ trả chunk `synthetic` hoặc `factory_confidential` (backend `memory` và `pgvector`).
- **AC-13** `search` với `{"kind": "table", "process_ids": "PACK01"}` chỉ trả chunk thỏa cả hai điều kiện.
- **AC-14** `index` một dòng JSONL sai schema → không chunk nào của file đó được ghi.
- **AC-15** Index lại cùng chunk → số dòng trong bảng không đổi.
- **AC-16** `KNOWHOW_EMBED_DIM` lệch cột `vector(N)` → lỗi rõ ràng khi khởi động.
- **AC-17** `--replace-doc DOC-<cũ>` → sau index, chunk của `DOC-<cũ>` không còn trong store, chunk mới còn; file lỗi hoặc `doc_id` sai dạng → không xóa gì.
- **AC-18** Trang chứa chuỗi sai mã hóa kiểu DOC-01 (`σϯιʔςΫχΧϧϨϏϡʔ…`) → log cảnh báo kèm số trang, file vẫn ra chunk; văn bản tiếng Việt/Nhật/Anh có ký hiệu kỹ thuật (Ω, Δ, µ) không bị cảnh báo.
- **AC-19** `KNOWHOW_DOC_EXTRACTOR=remote`, máy chủ giả lập trả `export_to_dict()` của một `DoclingDocument` (heading, đoạn văn, list, bảng, chữ OCR trong hình, caption, footer) → `RawDocument` bằng đúng kết quả của `docling_to_raw` trên chính document đó (`extractor = docling`); request là multipart `file` tới `/documents/convert` kèm Bearer key; máy chủ trả 422 → PDF chuyển sang mmore, lý do ghi `docling-remote`; thiếu `docling_core` → lỗi nêu cách cài; thiếu `KNOWHOW_INFERENCE_URL` → lỗi nêu tên biến; `KNOWHOW_INFERENCE_API_KEY` trống → key VLM chỉ khi `KNOWHOW_VLM_BASE_URL` cùng host (vendor cloud, hoặc host khác → không header); tệp tải lên không có trả lời trong timeout đọc hoặc nhận 504 → lỗi ngay, gửi đúng một lần; lỗi kết nối → thử lại; timeout kết nối 10 s.
- **AC-20** `KNOWHOW_EMBEDDER=remote`: 70 đoạn → 3 request (32, 32, 6); vector đúng thứ tự đầu vào dù máy chủ trả `data` đảo thứ tự, độ dài 1; số chiều khác `KNOWHOW_EMBED_DIM`, thiếu vector hoặc máy chủ lỗi → `VectorStoreError`; `get_vector_store` và Work Assistant (khi store không có embedder) dùng embedder này.
- **AC-21** URL máy chủ là host public không có trong `KNOWHOW_LOCAL_HOSTS` + `factory_confidential` → `ConfidentialDataError` và **không request nào được gửi**: `ingest run` với extractor `remote` (không ghi file), `upsert` chunk confidential, `search` (câu truy vấn không nhãn); `ingest index` chỉ báo lỗi file confidential, file public vẫn được index; cùng host đó khai báo trong `KNOWHOW_LOCAL_HOSTS` → được gửi.

## 6. Tasks
- [x] T02-0 Spike công cụ (mmore/Docling/Surya) — kết quả ở `docs/plans/02-spike-notes.md`.
- [x] T02-7 (S0-5) Review data sample → `docs/data/sample_review.md`; tạo `data/samples/docs/` (3 file AC-01) và `packing_sop_scan.pdf` (AC-07).
- [x] T02-1 Model `DocumentChunk` + test.
- [x] T02-2 Adapter mmore process (subprocess hoặc Python API) → `DocumentChunk`.
- [x] T02-3 Fallback Docling / Surya + logic chọn extractor (AC-03).
- [x] T02-4 Chunker (FR-04) + regex nhận diện (FR-05).
- [x] T02-5 CLI `ingest run` + idempotency (AC-04).
- [x] T02-6 CLI `ingest index` qua `VectorStore` (AC-06).
- [x] T02-8 Docling và bge-m3 trên máy chủ suy luận của đội: `core.providers.inference`, `RemoteDoclingExtractor`, `RemoteEmbedder` (FR-02c, FR-07d; AC-19..AC-21).
- [x] T02-9 Sửa sau review: key VLM chỉ cho máy chủ cùng host; tệp tải lên hết giờ chờ không gửi lại, kết nối tối đa 10 s (AC-19, AC-21).

## Changelog
- v1.0 (23/9): khởi tạo.
- v1.1 (23/9): thêm field `source_type` tường minh vào `DocumentChunk` (trước chỉ nằm trong metadata Milvus).
- v1.2 (27/9): index vào PostgreSQL/pgvector qua `VectorStore` thay cho Milvus/mmore index (FR-07, AC-06, T02-6).
- v1.3 (27/9): đường dẫn module theo layout mới (bỏ `knowhow.`/`src/knowhow/`, xem spec 01 v1.3).
- 1/10/2026 (Việt Hoàng): T02-1 xong — `core/schemas/document.py` (`ChunkKind`, `DocumentChunk` + validator), test `tests/core/schemas/test_document.py`; `make check` xanh.
- 1/10/2026 (Việt Hoàng): T02-4 xong — `capture/ingest/{raw,tokens,entities,chunker}.py`, thêm 7 setting ingest/chunk vào `Settings`; test AC-05, AC-10, FR-03/04/05; `make check` xanh.
- 1/10/2026 (Việt Hoàng): T02-6a xong (T02-6 chưa tick, còn pgvector + CLI) — `MemoryVectorStore` filter nhận list ("thuộc tập") và khóa `process_ids`/`part_numbers`/`doc_id`; test AC-12, AC-13, AC-15 trên backend memory; `make check` xanh.
- 1/10/2026 (Việt Hoàng): T02-0 spike xong (`docs/plans/02-spike-notes.md`). T02-2 + T02-3 xong **theo đề xuất 5 (phương án B, chờ Trung duyệt)**: `extractors/{base,docling,mmore}.py` + `select.py` — Docling chính cho pdf/docx/xlsx/pptx, mmore fast là fallback PDF (text-only, `metadata.degraded`), bỏ Surya đứng riêng; extra `ingest = ["docling"]`; chạy thật trên 4 file mẫu; `make check` xanh.
- 1/10/2026 (Việt Hoàng): T02-5 xong — `knowhow ingest run` (`ingest/{jsonl,pipeline,cli}.py`): `--classification` bắt buộc, ghi JSONL nguyên tử, chặn đổi nhãn khi chưa `--force`, một file lỗi không dừng cả lô (exit 1). Thêm setting `mmore_bin`, `token_counter`; nén padding bảng Docling. Chạy thật trên packing_sop.pdf, DOC-04, DOC-05: 40 chunk, lần 2 trùng từng byte (AC-04); `make check` xanh.
- 1/10/2026 (Việt Hoàng): T02-6c xong (T02-6 chưa tick, còn pgvector) — `knowhow ingest index` (`ingest/index.py`): validate cả file trước khi ghi (AC-14), upsert theo batch, idempotent (AC-15); thử trên 40 chunk thật với backend memory, filter `data_classification`/`kind`/`process_ids` đúng; `make check` xanh.
- 1/10/2026 (Việt Hoàng): T02-6 xong — `knowledge_base/store/pgvector_store.py` (`PgVectorStore`: upsert `ON CONFLICT`, tìm lai dense + full-text RRF trong 1 câu SQL, filter tham số hoá qua `parse_filters` dùng chung với backend memory, AC-16 kiểm `vector(N)` lúc khởi động); thêm `psycopg[binary]` vào extra `ingest`; marker `integration`. Chạy thật trên PostgreSQL: nạp ở tiến trình này, tìm ở tiến trình khác; AC-06/12/13/15/16 pass. **Còn thiếu:** embedder bge-m3 thật (tạm `KNOWHOW_EMBEDDER=hashing`, mặc định `bge-m3` bị từ chối); `make check` xanh (375 test).
- 1/10/2026 (Việt Hoàng): thêm `BgeM3Embedder` (`store/embedder.py`: vector [CLS] bge-m3, chuẩn hoá L2, batch 16, nạp lười) làm embedder mặc định cho pgvector; thêm `transformers`/`torch` vào extra `ingest` (lock không đổi). Kiểm trên model thật: cos 0,736 (câu đúng nghĩa) vs 0,412 (sai nghĩa) vs 0,627 (câu tiếng Nhật cùng nghĩa); nạp lại 40 chunk bằng bge-m3. `make check` xanh (381 test).
- v1.4 (3/10, Việt Hoàng): đồng bộ spec với code và `docs/plans/02-ingest-index-spec.md` — Docling là extractor chính, mmore fast là fallback PDF, bỏ Surya đứng riêng (FR-02, §2; đề xuất 5, chờ Trung duyệt); thêm FR-01b, FR-07b, bảng lớn tách theo hàng (FR-03), stoplist/regex part number (FR-05); thêm AC-07..AC-16 và task T02-0, T02-7. AC-02 chưa đổi (đề xuất 3 chờ duyệt); đánh giá theo trang và FR-02b chưa làm (đề xuất 1–2).
- 3/10/2026 (Việt Hoàng): tạo `data/samples/docs/` (packing_sop.pdf, packing_sop_scan.pdf qua `scripts/make_scan_sample.py`, sps_form_12_1_14.xlsx) và `tests/capture/ingest/test_samples.py` (AC-01..03 chạy Docling thật, bật bằng `KNOWHOW_RUN_SAMPLE_TESTS=1`): 3 pass, 42 chunk. T02-7 chưa tick (còn video, SQAM 2024, quyền DOC-03). `make check` xanh.
- 3/10/2026 (Việt Hoàng): sửa lỗi mất trang ảnh — `docling_to_raw` bỏ `picture` nên chữ OCR trong bản vẽ (DOC-04 tr. 3) biến mất; nay gom chữ con của picture thành block `drawing_note`. Docling mặc định đã OCR vùng ảnh nên không cần chọn extractor theo trang. Test `test_ac_03_text_inside_a_picture...` + AC-03 thật trên DOC-04 (tr. 3 có `TN057763-7131`), 4 test mẫu pass; `make check` xanh (368 test).
- 3/10/2026 (Việt Hoàng): end-to-end S2-5 trên PostgreSQL/pgvector thật (docker `postgres`): `ingest run` 3 file mẫu + DOC-04 → `ingest index` 59 chunk (bge-m3); `search` lọc `data_classification` public/synthetic/factory_confidential, `kind`, `kind`+`process_ids` đều trả đúng, không lẫn nhãn. 16 test `integration` pass; `make check` xanh.
- 3/10/2026 (Việt Hoàng): đo OCR tiếng Việt trên scan giả (3 cấu hình, xem `docs/plans/02-spike-notes.md`): RapidOCR mặc định tốt nhất cho `PACK01`; giữ nguyên, không đổi code/phụ thuộc.
- 3/10/2026 (Việt Hoàng): T02-7 phần đo đã xong — ingest Docling thật trên DOC-01/02/03 + SQAM 2024 (bảng ở `docs/data/sample_review.md`): DOC-01 → ACCEPT. Sửa 2 lỗi lộ ra: chunker tách bảng có dòng tiêu đề trước `|` (chunk không hợp lệ), và `ValidationError` làm dừng cả lô (nay báo lỗi riêng file đó). Test mới trong test_chunker/test_pipeline; `make check` xanh (385 test). T02-7 chưa tick: còn chờ nhãn SQAM 2024, quyền DOC-03, quyết định về video.
- 3/10/2026 (Việt Hoàng): T02-7 xong — mọi file có kết luận ACCEPT/REDO (AC-07): DOC-01..05 + PACK01 ACCEPT, SQAM 2024 REDO (thiếu nhãn/nguồn; giữ ngoài repo). DOC-03 đã có sẵn trong repo nên không copy vào `data/samples/docs/` (PDF text mẫu = `packing_sop.pdf`); video thuộc S0-7 (spec 03), ngoài phạm vi.
- 3/10/2026 (Việt Hoàng): đồng bộ `docs/plans/02-ingest-index-spec.md` v0.2 với code và `init.sql`; đối chiếu enum `data_classification` của `assets`/`document_chunks`/`knowhow_chunks` trong `init.sql`: khớp Điều 2.
- 3/10/2026 (Việt Hoàng): `--replace-doc` xong (FR-07c, AC-17): `VectorStore.delete_where` (memory + pgvector, từ chối filter rỗng), `replace_docs`, tùy chọn CLI; xóa sau khi index, bỏ qua nếu có file lỗi. Test unit + integration (pgvector thật); `make check` xanh.
- 3/10/2026 (Việt Hoàng): FR-02b xong ở dạng cảnh báo (AC-18): `capture/ingest/quality.py`, setting `text_quality_max_odd_ratio`, cảnh báo trong dòng log. Đo trên 4 tài liệu thật (DOC-01, DOC-02, 2 bản SQAM): trang xấu nhất 1,0% (bài báo có công thức) so với ngưỡng 5%, không báo nhầm. Chưa kiểm được ca dương thật: pdfium đọc đúng DOC-01 (chỉ pypdf ra rác), nên test dùng chuỗi rác trích từ review. `make check` xanh.
- v1.5 (08/10, Phúc): extract/OCR và embed chạy được trên máy chủ suy luận riêng của đội (`KNOWHOW_INFERENCE_URL`; `KNOWHOW_DOC_EXTRACTOR=remote`, `KNOWHOW_EMBEDDER=remote`), thay câu "Tất cả chạy local" ở §2: local/cloud theo URL + `KNOWHOW_LOCAL_HOSTS` như VLM, không bao giờ dùng API OCR/embedding bên thứ ba; FR-01b một lần `DataGuard` mỗi lượt, kể cả extractor gửi file đi; FR-02c, FR-07d (câu truy vấn không nhãn coi là `factory_confidential`). AC-19..AC-21, T02-8.
- v1.6 (08/10, Phúc, review): §2 key `KNOWHOW_VLM_API_KEY` chỉ thay key trống khi VLM cùng host với máy chủ suy luận (trước đây key ép cho vendor cloud đi tới máy chủ suy luận, kể cả qua HTTP thường); kết nối tối đa 10 s, tệp tải lên hết giờ chờ trả lời hoặc 504 không gửi lại (trước đây gửi lại 2 lần, xếp hàng sau chính nó: lỗi sau 90 phút, máy chủ làm 3 lần). (Tra theo filter không embed đã bỏ: remote chỉ dùng với máy chủ khai báo local, logic gốc giữ nguyên.)
- v1.7 (08/10, Phúc): FR-07d ghi rõ phạm vi chế độ remote (máy chủ của đội, khai báo local; demo dùng remote, thực tế local); không làm FR-09b cho URL cloud — chốt finding review remote-6/process-1.
