# Plan — Ingest & Index (Việt Hoàng)

Spec: `docs/plans/02-ingest-index-spec.md` · Deadline nộp: 12/10/2026 · Hôm nay: 29/9.
Quy trình mỗi task theo CLAUDE.md: viết test từ AC trước → code tối thiểu → `make check` xanh → tick task + changelog trong spec.

## Thứ tự và phụ thuộc
```
T02-7 (review data, S0-5) ──┐
T02-0 (spike công cụ) ──────┼─► T02-3 fallback ─► T02-5 CLI run ─► T02-6 index
T02-8 (bản tối thiểu deps) ─┤        ▲                                  ▲
T02-1 model ────────────────┴─► T02-2 mmore ─► T02-4 chunker ─────────┘
```
`make check` cần `pyproject.toml`/`Makefile` (T01-1, Trung). Nếu chưa có khi bắt đầu, dựng bản tối thiểu ở T02-8 để chạy `pytest` + `ruff` + `mypy`, Trung thay sau.

## Giai đoạn 0 — Chuẩn bị (29–30/9)
| Task | Nội dung | Ra gì | Xong khi |
|---|---|---|---|
| **T02-7** (S0-5) | Tải DOC-05 (+ DOC-04 nếu được); review từng file theo spec §3.2; tạo `packing_sop_scan.pdf`; chọn bộ 3 file AC-01 | `docs/data/sample_review.md`, `data/samples/docs/*` | AC-07: mọi file có kết luận ACCEPT/REDO |
| **T02-0** | Spike: cài mmore (CPU), Docling, Surya trên máy dev; chạy mỗi công cụ trên 1 file; ghi định dạng đầu ra, thời gian, lỗi | Ghi chú trong PR/changelog + mẫu đầu ra thô | Biết chắc API/đầu ra để viết adapter; nếu công cụ không cài được thì báo Trung ngay |
| **T02-8** | Bản tối thiểu: `core/schemas/common.py` (`DataClassification`), `VectorStore` Protocol + `VectorChunk`/`VectorHit`/`Filters` + backend `memory` + `get_vector_store()`, `pyproject.toml` extras `ingest`/`ingest-ocr` nếu chưa có | Code ở đúng đường dẫn spec 01 | Trung/Vinh xác nhận interface (đặc biệt "store tự embed") |

Chốt trong giai đoạn này (hỏi Trung/Vinh/dendeqwe): (1) store tự embed; (2) `knowhow_chunks` thêm vào `init.sql`; (3) `CHECK` classification của `assets`/`document_chunks`.

## Giai đoạn 1 — Ingest lõi (1–4/10)
| Task | AC | Ghi chú |
|---|---|---|
| **T02-1** Model `DocumentChunk` + validator | chunk_id, kind=table markdown, không rỗng | Test trước; `mypy --strict` áp dụng cho `core/schemas` |
| **T02-2** Adapter mmore → `DocumentChunk` | AC-01 (PDF text, XLSX), AC-02 | `Extractor` interface + `FakeExtractor`; XLSX giữ đủ hàng/cột |
| **T02-4** Chunker + regex | FR-03/04/05, AC-10 | Đếm token bằng tokenizer bge-m3; bảng lớn tách theo hàng, lặp header |
| **T02-3** Docling/Surya + chọn extractor | AC-03, AC-11 | Ngưỡng 50 ký tự/trang; log lý do chuyển extractor |

## Giai đoạn 2 — CLI và idempotency (5–7/10)
| Task | AC | Ghi chú |
|---|---|---|
| **T02-5** `knowhow ingest run` | AC-04, AC-05, AC-08, AC-09 | `--classification` bắt buộc; ghi file tạm rồi rename; log FR-08 |
| Chạy trên 3 file AC-01 | AC-01..03 | Đây là DoD của S1-1; báo cáo số chunk, extractor, thời gian |

## Giai đoạn 3 — Index (7–9/10)
| Task | AC | Ghi chú |
|---|---|---|
| **T02-6a** Backend `memory`: filter + upsert idempotent | AC-12, AC-13, AC-15 (memory) | Chạy được trong CI không docker |
| **T02-6b** Backend `pgvector` + DDL `knowhow_chunks` | AC-06, AC-12/13/15 (pgvector), AC-16 | Cần `make up` (Vinh); kiểm `unaccent` trong generated column |
| **T02-6c** CLI `ingest index` | AC-14 | Validate trước khi ghi; batch embed |

## Giai đoạn 4 — Tích hợp và đệm (9–11/10)
- Chạy end-to-end: `ingest run` → `ingest index` → `search(filter)` trên 3 file mẫu; kiểm `data_classification` lọc đúng.
- Ghép với `make demo` (M8) cùng đội; SOP PACK01 phải ra được chunk để agent cite.
- Đệm cho lỗi công cụ OCR và review của Trung. 12/10 nộp.

## Phân cấp ưu tiên (Điều 7)
- **Must:** T02-1, T02-2, T02-4, T02-5, T02-6, T02-7; đường mmore + XLSX + bảng.
- **Must nhưng có thể rút gọn:** T02-3 — nếu Surya cài không nổi trên CPU, giữ Docling; ghi rõ trong changelog.
- **Could (không làm trước khi Must xong):** `ingest probe` (báo cáo tự động chars/trang cho S0-5), `--replace-doc`, `figure_caption`/`drawing_note` chi tiết, ColPali.

## Việc cần người khác
| Việc | Ai | Cần trước |
|---|---|---|
| `pyproject.toml`, `Makefile`, CI | Trung (T01-1, T01-6) | 1/10 |
| Xác nhận interface `VectorStore` | Trung/Vinh | 30/9 |
| `docker-compose.yml`, `knowhow_chunks` trong `init.sql` | Vinh, dendeqwe | 7/10 |
| Chốt enum classification cho `init.sql` | Trung + dendeqwe | 30/9 |
| Xác nhận được phép commit DOC-03 vào `data/samples/` | Đạt (PM) | 30/9 |

## Kiểm tra trước khi đóng từng task
1. Mỗi `AC-xx` có test `test_ac_xx_...`; test không gọi mạng.
2. `make check` xanh.
3. Không commit file trong `data/raw/`, `data/factory/`, `data/work/`.
4. Tick `[x]` task và ghi 1 dòng changelog vào spec 02.
