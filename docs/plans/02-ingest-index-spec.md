# 02b — Ingest & Index: spec chi tiết cho phần của Việt Hoàng

**Owner:** Việt Hoàng · **Tasks Excel:** S0-5, S1-1, S2-5 · **Bổ sung cho:** `docs/02-document-ingest-ocr.md`
**Trạng thái:** v0.2 (3/10) — đã triển khai và đồng bộ vào `docs/02-document-ingest-ocr.md` v1.4. Tài liệu này giữ lại làm lý do thiết kế; khi lệch, **spec gốc và `infra/postgres/init.sql` thắng**. Các mục còn chờ Trung duyệt nằm ở `02-spec-change-proposal.md`.

## 1. Phạm vi
Ba việc, theo thứ tự phụ thuộc:

| # | Việc | Task Excel | DoD |
|---|---|---|---|
| A | Review data sample | S0-5 | Bảng chấp nhận / yêu cầu làm lại cho từng file |
| B | OCR + ingest → `DocumentChunk` JSONL | S1-1 | 3 file mẫu đều ra chunk, bảng giữ nguyên cấu trúc |
| C | Index chunk vào PostgreSQL/pgvector | S2-5 | Truy vấn filter (đặc biệt `data_classification`, `kind`) chạy đúng |

Ngoài phạm vi: agent/retriever hybrid (spec 05/06), graph, UI, video.

## 2. Quyết định đã chốt (brainstorm 29/9)
| Chủ đề | Quyết định |
|---|---|
| Bảng vector | Một bảng dùng chung `knowhow_chunks` (`KNOWHOW_VECTOR_TABLE`), phân biệt bằng `source_type`. `init.sql` (`public.knowhow_chunks`) là định nghĩa bảng; bảng `document_chunks` trong `init.sql` chỉ là bản ghi parse, không dùng để tìm kiếm. |
| Enum `data_classification` | `public` \| `synthetic` \| `factory_confidential` (Constitution Điều 2). `init.sql` đã dùng domain `public.data_classification` với đúng 3 giá trị này cho `assets`, `document_chunks`, `knowhow_chunks` (đối chiếu 3/10: khớp). `source_label` (`public`/`denso_internal`/`partner`) là nguồn gốc, không phải nhãn nhạy cảm. |
| Phụ thuộc chưa có | Tự dựng bản **tối thiểu** ở đúng đường dẫn spec 01; Trung/Vinh thay bằng bản đầy đủ sau, không đổi interface. |
| Sample AC-01 | PDF text = DOC-03; XLSX = tải DOC-05; PDF scan = bản scan giả tạo từ `packing_sop.pdf`, gắn `synthetic`. |

## 3. Việc A — Review data sample (S0-5)

### 3.1 Input
- `docs/data/MentorMind_Sample_Data.xlsx` (DOC-01..05, nhãn nguồn `public`).
- File trong repo: `data/09-1-doc-dissertation14-id-ja.pdf`, `data/24-doc-15-paper-10.pdf`, `data/NA Final SQAM 20220627.pdf`, `data/demo/packing/packing_sop.pdf` (+ `packing_sop_source.md` làm đáp án).
- Cần tải: DOC-04 `6-7-NASWEB-Supplier-Label-Tech-Spec.pdf`, DOC-05 `sps_form_12_1_14.xlsx`.

### 3.2 Tiêu chí review (mỗi file một dòng)
| Tiêu chí | Cách kiểm | Ngưỡng chấp nhận |
|---|---|---|
| Mở được | Mở bằng thư viện, không lỗi/mật khẩu | Bắt buộc |
| Text layer | Ký tự trung bình/trang (trang có chữ) | ≥ 50 → đường mmore; < 50 → coi là scan (FR-02) |
| Ngôn ngữ | Người review đọc tiêu đề + 1 trang | Ghi EN/JA/VI; JA phải qua được bge-m3 |
| Chất lượng scan | Quan sát: độ phân giải, nghiêng, nhiễu, chữ mờ | Chữ chính đọc được bằng mắt ở 100% |
| Bảng | Đếm bảng chính, kiểm tra đường kẻ/ô gộp | Ghi số bảng; ô gộp nhiều tầng → cảnh báo |
| Nhãn phân loại | Đối chiếu nguồn | Nguồn công khai → `public`; do đội tạo → `synthetic`; không có nhãn rõ → **yêu cầu làm lại** |
| Bản quyền/redistribute | Đọc `license_note`/trang nguồn | File commit vào `data/samples/` phải được phép phát hành lại; không rõ → chỉ để ngoài repo |
| Khả năng dùng làm test | Có đáp án đối chiếu không | Có → dùng cho AC; không → chỉ dùng demo |

### 3.3 Output
`docs/data/sample_review.md`, bảng: `ID | file | text layer | ngôn ngữ | scan quality | số bảng | nhãn | kết luận (ACCEPT / REDO) | lý do / việc cần làm`. Mỗi `REDO` có hành động cụ thể (tải lại, scan lại, gán nhãn).

### 3.4 Dự kiến kết quả (giả thuyết ban đầu — đã có số đo thật ở `docs/data/sample_review.md`)
Giả thuyết viết trước khi chạy công cụ nào; giữ lại để đối chiếu.
- DOC-01/02: tiếng Nhật, text layer; kiểm chứng ingest tiếng Nhật, nhãn `public`.
- DOC-03: EN, dài, có bảng; là ứng viên PDF text cho AC-01. Ghi chú nguồn nói trang gốc có thể yêu cầu quyền truy cập → kiểm tra quyền phát hành lại.
- DOC-04: layout + bảng label, dùng test bảng.
- DOC-05: XLSX gốc, parse native, ứng viên AC-02.
- `packing_sop.pdf`: `synthetic`, có bản gốc markdown để đối chiếu; nguồn để tạo bản scan giả cho AC-03.

## 4. Việc B — Ingest (S1-1)

### 4.1 Model `DocumentChunk`
Đúng như spec 02 §3, đặt tại `mentormind/core/schemas/document.py`; `DataClassification` tại `mentormind/core/schemas/common.py`.
Ràng buộc bổ sung (validator Pydantic):
- `chunk_id` khớp `^DOC-[0-9a-f]{12}#p\d+-\d+$`; với file không có trang (DOCX/XLSX) `page` = số thứ tự sheet/section, tên gốc lưu ở `metadata.sheet_name`.
- `kind == table` ⇒ `text` là markdown table hợp lệ (có dòng phân cách `---`).
- `text` không rỗng; `process_ids`/`part_numbers` không trùng lặp, sắp xếp ổn định (để idempotent).

### 4.2 Chọn extractor (FR-02)
```
mmore → chars/page trung bình ≥ 50 ? dùng kết quả mmore
      : Docling(OCR) → lỗi/0 chunk ? Surya
```
- Trung bình tính trên các trang, không phải trên toàn file.
- Sinh `extractor` vào từng chunk; log lý do chuyển extractor (FR-08).
- XLSX/DOCX/PPTX: không bao giờ OCR; nếu mmore lỗi thì báo lỗi rõ ràng, không rơi sang Docling.
- Extractor đứng sau interface `Extractor` (Constitution Điều 5); test dùng `FakeExtractor`.

### 4.3 Chunker (FR-03, FR-04)
- Bảng: 1 bảng = 1 chunk `kind=table`, markdown table.
- **Bảng quá lớn** (> 800 token, ví dụ bảng trong SQAM): tách theo hàng, lặp header ở mỗi phần, `kind=table`, `metadata.table_part = "i/n"`. **Đề xuất sửa spec** (mục 9) vì FR-03 nói "mỗi bảng 1 chunk" nhưng FR-04 giới hạn 800 token.
- Văn bản: 300–800 token, overlap 50, không cắt ngang bảng; cắt ưu tiên theo heading/đoạn.
- Đếm token bằng tokenizer bge-m3 (`KNOWHOW_EMBED_MODEL`) để khớp với bước embed.
- `figure_caption`, `drawing_note` chỉ gán khi extractor cung cấp loại block tương ứng; nếu không có thì là `text`.

### 4.4 Nhận diện mã (FR-05)
- `process_ids`: `KNOWHOW_PROCESS_ID_REGEX`, mặc định `\b[A-Z]{3,5}\d{2}\b`.
- `part_numbers`: `KNOWHOW_PART_NUMBER_REGEX` (mới), mặc định do Việt Hoàng chọn sau khi xem sample; ghi cùng chỗ với regex trên.
- Lưu ý regex mặc định sẽ khớp cả chuỗi không phải mã công đoạn (VD `ISO27`, `REV01`); chấp nhận ở MVP, có `KNOWHOW_PROCESS_ID_STOPLIST` để loại.

### 4.5 CLI (FR-01, FR-06, FR-08)
```
knowhow ingest run --input <dir|file> --classification <public|synthetic|factory_confidential> --out data/work/chunks/
```
- `--classification` **bắt buộc**, không có mặc định; sai giá trị → lỗi, không ghi file.
- Một JSONL cho mỗi file nguồn: `<doc_id>.jsonl`. Ghi qua file tạm rồi rename để không để lại file dở.
- Định dạng hỗ trợ: `.pdf .docx .xlsx .pptx`; định dạng khác → bỏ qua và log `skipped`.
- Idempotent: `doc_id = "DOC-" + sha256(bytes)[:12]`; chạy lại ghi đè cùng file, cùng `chunk_id`, cùng thứ tự dòng.
- Cùng file chạy lại với `--classification` khác → **lỗi** (tránh hạ nhãn mật một cách vô tình); phải xóa output cũ hoặc dùng `--force`.
- Log mỗi file: extractor, số trang, số chunk, thời gian.

### 4.6 DataGuard
OCR/embed chạy local nên không có provider `is_cloud`. Vẫn gọi `DataGuard.check(classification, provider)` với provider local để giữ điểm chặn tập trung cho khi đổi provider (Điều 5). Không gọi mạng ngoài trong bất kỳ bước nào của spec này.

## 5. Việc C — Index (S2-5)

### 5.1 Interface (spec 01 FR-05c)
Mã nguồn: `mentormind/core/schemas/vector.py` (`VectorChunk`, `VectorHit`) và `mentormind/knowledge_base/store/vector_store.py` (`VectorStore`, `Embedder`, backend `memory`, `get_vector_store()`); backend pgvector ở `pgvector_store.py`, embedder bge-m3 ở `embedder.py`.
```python
SourceType = Literal["work_profile", "document", "video_segment", "sigma"]


class VectorChunk(BaseModel):
    chunk_id: str  # khóa upsert
    source_type: SourceType
    ref_id: str  # Citation.ref_id: doc_id với tài liệu
    text: str
    kind: str | None = None
    process_ids: list[str] = []
    part_numbers: list[str] = []
    data_classification: DataClassification
    metadata: dict[str, Any] = {}
    embedding: list[float] | None = None  # store tự điền nếu thiếu


class VectorStore(Protocol):
    def upsert(self, chunks: Iterable[VectorChunk]) -> int: ...
    def search(self, query: str, k: int = 8, filters: Mapping[str, Any] | None = None) -> list[VectorHit]: ...
    def delete(self, ids: Iterable[str]) -> int: ...
```
- **Store tự embed** văn bản khi `upsert` và câu truy vấn khi `search` (qua `Embedder` được inject): đã triển khai (FR-07b trong spec gốc).
- `Filters` là dict: `{"kind": "table"}` (bằng), `{"data_classification": ["public","synthetic"]}` (thuộc tập), `{"process_ids": "PACK01"}` (mảng chứa giá trị). Nhiều khóa = AND. Khóa lạ bị từ chối, không bao giờ vào SQL.
- `get_vector_store()` chọn `pgvector` | `memory` theo `KNOWHOW_VECTOR_BACKEND`; embedder theo `KNOWHOW_EMBEDDER` (`bge-m3` | `hashing`).

### 5.2 Bảng `knowhow_chunks` (pgvector)
DDL nằm ở `infra/postgres/init.sql` (mục "Vector table"), không lặp lại ở đây. Điểm cần nhớ:
- Cột: `chunk_id` (PK), `source_type`, `ref_id`, `kind`, `text`, `process_ids text[]`, `part_numbers text[]`, `data_classification` (domain 3 giá trị), `metadata jsonb`, `embedding vector(1024)`, `search_tsv` (sinh từ cấu hình `public.mm_unaccent`), `created_at`, `updated_at`.
- Chỉ mục: HNSW cosine trên `embedding`, GIN trên `search_tsv` và `process_ids`, B-tree trên `(source_type, kind)`, `(source_type, ref_id)`, `data_classification`.
- Vấn đề `unaccent` trong generated column đã giải quyết bằng text search configuration `mm_unaccent` (to_tsvector(regconfig, text) là immutable); xem comment trong `init.sql`.
- `vector(1024)` phải bằng `KNOWHOW_EMBED_DIM`; store kiểm khi khởi động và báo lỗi nếu lệch (AC-16).
- `upsert` dùng `INSERT ... ON CONFLICT (chunk_id) DO UPDATE`; chạy lại không nhân đôi. Khi file nguồn đổi (hash mới → `doc_id` mới) chunk cũ không bị xóa tự động; xóa bằng `ingest index --replace-doc <doc_id cũ>` (FR-07c) hoặc `VectorStore.delete_where`.
- Trigger trong `init.sql` chỉ cho chunk `work_profile` của profile đã `approved`; không ảnh hưởng chunk tài liệu.

### 5.3 CLI (FR-07)
```
knowhow ingest index --chunks data/work/chunks/ [--batch-size 32]
```
- Đọc mọi `*.jsonl`, validate từng dòng bằng `DocumentChunk`; dòng lỗi → dừng, báo `file:dòng`, không ghi gì cho file đó.
- Embed theo batch, upsert theo batch; in tổng: đã upsert / bỏ qua / lỗi.
- Ánh xạ `DocumentChunk` → `VectorChunk`: `text`, `kind`, `doc_id`, `process_ids`, `data_classification`; `page`, `title`, `source_path`, `part_numbers`, `extractor` vào `metadata`.

## 6. Acceptance Criteria
Giữ nguyên AC-01..AC-06 của spec 02, thêm các AC sau (đánh số tiếp):

- **AC-07** (A) `docs/data/sample_review.md` có 1 dòng cho mỗi file trong danh sách 3.1, đủ mọi cột, mỗi `REDO` có hành động.
- **AC-08** `ingest run` thiếu `--classification` hoặc giá trị ngoài enum → lỗi, không ghi file.
- **AC-09** Chạy lại cùng file với `--classification` khác → lỗi; với `--force` → ghi đè.
- **AC-10** Bảng lớn hơn 800 token → nhiều chunk `kind=table`, mỗi chunk có header lặp lại và `metadata.table_part`.
- **AC-11** Extractor lỗi (FakeExtractor raise) → chuyển sang extractor tiếp theo; cả ba lỗi → file được báo lỗi, các file khác vẫn xử lý.
- **AC-12** `VectorStore.search` với `filters={"data_classification": ["public"]}` không bao giờ trả chunk `synthetic` hoặc `factory_confidential` (test trên backend `memory` và `pgvector`).
- **AC-13** `search` với `{"kind":"table","process_ids":"PACK01"}` chỉ trả chunk thỏa cả hai điều kiện.
- **AC-14** `index` một dòng JSONL sai schema → không chunk nào của file đó được ghi.
- **AC-15** Index lại cùng chunk → `SELECT count(*)` không đổi (idempotent).
- **AC-16** `KNOWHOW_EMBED_DIM` lệch với cột `vector(N)` → lỗi rõ ràng khi khởi động.

Test integration (AC-06, AC-12/13/15 trên pgvector) đánh dấu `@pytest.mark.integration`, chỉ chạy khi `make up`. Unit test dùng `FakeExtractor`, `FakeEmbedder` và backend `memory`, không gọi mạng (Điều 6).

## 7. Sample cho AC-01..AC-03
Đặt tại `data/samples/docs/` (được commit theo FR-06):
| File | Vai trò | Nhãn | Nguồn |
|---|---|---|---|
| `packing_sop.pdf` | PDF text | synthetic | thay DOC-03 (đã có sẵn trong `data/`, dùng cho ca bảng lớn AC-10); có đáp án `packing_sop_source.md` |
| `sps_form_12_1_14.xlsx` | XLSX, bảng | public | DOC-05, tải mới |
| `packing_sop_scan.pdf` | PDF scan | synthetic | rasterize `packing_sop.pdf`, thêm nghiêng/nhiễu nhẹ; đối chiếu với `packing_sop_source.md` |

DOC-01/02/04 dùng cho kiểm thử tiếng Nhật và bảng, không bắt buộc commit.

## 8. Rủi ro
| Rủi ro | Giảm thiểu |
|---|---|
| Chưa xác minh API/đầu ra thực tế của mmore, Docling, Surya trên máy dev (chưa cài) | T02-0 spike trước khi cam kết adapter; adapter đứng sau interface |
| Docling/Surya nặng, chạy chậm trên CPU/Mac | Ghi thời gian ở T02-0; chỉ dùng cho file scan; test dùng fake |
| Bảng tiếng Nhật/ô gộp mất cấu trúc | Ghi vào review (3.2); AC-02 kiểm bằng XLSX, không bằng PDF |
| Regex `process_ids` khớp nhầm | Stoplist + cấu hình được |
| `unaccent` trong generated column | Kiểm ở T02-6 |
| Phụ thuộc T01-1/T01-3/T01-7 (Trung/Vinh) chưa xong | Bản tối thiểu ở mục 5.1, thay sau không đổi interface |

## 9. Đề xuất sửa spec — trạng thái (3/10)
- **`docs/02-document-ingest-ocr.md`:** FR-01b, FR-03 (bảng lớn), FR-07b, AC-07..AC-16, T02-0 và T02-7 đã áp dụng vào spec gốc (v1.4). Các đề xuất 1–5 về extractor/AC-02/AC-03 nằm ở `02-spec-change-proposal.md` (đề xuất 5 đã được code theo, chờ Trung duyệt).
- **`infra/postgres/init.sql`:** đã có `public.knowhow_chunks` và domain `public.data_classification` đúng Điều 2 cho cả `assets`, `document_chunks`, `knowhow_chunks`. Không còn vấn đề enum.

## Changelog
- v0.1 (29/9): khởi tạo từ brainstorm.
- v0.2 (3/10): đồng bộ với code: `VectorChunk` có `ref_id`/`part_numbers`/`embedding`, DDL chuyển sang `init.sql`, bỏ ghi chú 'chờ xác nhận' của store tự embed, mục 9 thành bảng trạng thái, mẫu AC-01 dùng `packing_sop.pdf`.
