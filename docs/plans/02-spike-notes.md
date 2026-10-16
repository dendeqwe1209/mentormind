# T02-0 — Spike công cụ ingest (1/10/2026)

Máy: MacBook Apple Silicon, **chỉ CPU**, Python 3.11. Cài trong venv riêng (không đụng `.venv` của repo).
Phiên bản: mmore 2.0.0 (`mmore[process]`, kéo theo marker-pdf 1.10.2 + surya-ocr 0.17.1), docling 2.132.0.
Mẫu đầu ra thô (chỉ file `synthetic`): `tests/fixtures/ingest/`.

## Kết quả đo

| | mmore fast | mmore đầy đủ | Docling |
|---|---|---|---|
| Cấu hình | `use_fast_processors: true` | `use_fast_processors: false` | `DocumentConverter().convert(path)` |
| PDF text (SOP, 3 trang) | ~3 s | (gộp bên dưới) | 10 s (lần 2), 58 s (lần 1, tải model) |
| PDF 9 trang có 2 trang ảnh (DOC-04) | ~3 s | 2 file mất 300 s gồm tải model, ~100 s/file | 37 s |
| Dung lượng model | 0 | **3,3 GB** (`~/Library/Caches/datalab`) | **529 MB** (`~/.cache/huggingface`) |
| Bảng PDF | **mất cấu trúc** (mỗi ô một dòng) | markdown table đúng (SOP 41 dòng bảng) | markdown table đúng (SOP 7 bảng; DOC-04 4 bảng) |
| Trang chỉ có ảnh (DOC-04 tr. 3, 6) | bỏ sót (32–33 ký tự) | OCR được (7.182 → 20.825 ký tự) | có khối (22.984 ký tự); log "RapidOCR returned empty result" ở vài vùng |
| Ranh giới trang | `metadata.paragraph_starts` = `[offset, page(0-based), para]` | cùng trường, page **1-based** | `prov.page_no` từng khối (1-based) |
| XLSX | dump pandas (`Unnamed: 0`, `NaN`), có `Sheet: <tên>` | không qua marker | **0,6 s**, 4 bảng thật (39×18, …), markdown table |
| Đầu ra | JSONL `{text, modalities, metadata}`; `metadata.processor_type` | như fast | `doc.export_to_markdown()`, `doc.tables`, `iterate_items()` |

DOC-01 (tiếng Nhật): mmore fast **đọc đúng** chữ Nhật (bản `pypdf` trong `sample_review.md` đọc sai) → không phải REDO; FR-02b hạ xuống Should.

## Phát hiện làm lệch spec/plan

1. **Surya không phải fallback riêng**: `mmore[process]` kéo Surya vào qua marker. Cài `ingest-ocr` riêng là thừa.
2. **mmore fast không đạt FR-03** (bảng mất cấu trúc); mmore đầy đủ đạt nhưng nặng (3,3 GB, ~100 s/file CPU).
3. **Docling đạt cả bảng, OCR trang ảnh và XLSX** với 529 MB và nhanh hơn. Spec hiện coi Docling chỉ là fallback cho scan.
4. mmore chỉ `process` cho ra JSONL theo file, không có khối `kind` (table/text); loại khối phải suy từ markdown.
5. mmore `process` cần file YAML (`data_path`, `dispatcher_config.{output_path,use_fast_processors,extract_images}`), tự quét thư mục, không có API gọi một file.
6. Chưa thử: Surya đứng riêng (không cần: đi kèm mmore), scan thật (mới có trang ảnh trong DOC-04; `packing_sop_scan.pdf` chưa tạo), Docling trên DOC-01.

## Quyết định cần Trung (spec 02 FR-02 / AC-03, DoD S1-1 ghi "mmore CPU + Docling/Surya")

| Phương án | Ưu | Nhược |
|---|---|---|
| A. Giữ spec: mmore trước, Docling sau | đúng DoD, giữ vai trò mmore | mmore fast mất bảng → luôn phải chạy mmore đầy đủ (3,3 GB, chậm) hoặc tự dựng bảng |
| B. Docling là extractor chính cho mọi định dạng; mmore chỉ dùng chế độ fast để lấy text thô/đối chiếu | một đường, bảng + XLSX + OCR, nhẹ | lệch DoD "mmore CPU"; phải sửa FR-02, AC-03 |
| C. mmore đầy đủ làm chính, Docling cho XLSX | giữ mmore | nặng, hai đường |

Đề xuất của người làm: **B**, vì chỉ Docling đạt FR-03 + AC-02 với chi phí hợp lý. Chưa áp dụng; chờ Trung duyệt (CLAUDE.md: spec mâu thuẫn thì dừng).

## OCR tiếng Việt trên bản scan giả (3/10/2026)

Đo trên `data/samples/docs/packing_sop_scan.pdf`, so với text layer của `packing_sop.pdf` (độ giống ký tự sau khi bỏ dấu câu/khoảng trắng; chỉ để so sánh tương đối).

| Cấu hình Docling | Độ giống | Nhận xét |
|---|---|---|
| RapidOCR mặc định (đang dùng) | 0,843 | Sai dấu tiếng Việt ("QUY TRINH THAO TÁC CHUN") nhưng giữ đúng `PACK01` |
| RapidOCR `lang=["latin"]` (cần onnxruntime) | 0,779 | Kém hơn mặc định |
| RapidOCR `lang=["vi"]` | 0,843 | Như mặc định (không có model riêng) |
| EasyOCR `["vi","en"]` (cần cài easyocr) | 0,271 | Dấu tiêu đề đúng ("QUY TRÌNH THAO TÁC CHUẨN") nhưng đọc `PACK01` thành `PACKO1` và rụng nhiều ô bảng |

**Quyết định:** giữ RapidOCR mặc định, không thêm phụ thuộc. `process_ids` (PACK01) quan trọng hơn dấu cho retrieval, và bge-m3 + tìm full-text `unaccent` chịu được sai dấu. Chỉ xét lại khi có scan thật; hướng thử tiếp là Tesseract `vie` (cần cài ngoài).
