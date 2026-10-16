# Đề xuất sửa `docs/02-document-ingest-ocr.md` (chờ Trung duyệt)

Người đề xuất: Việt Hoàng · Viết 29/9/2026, cập nhật 3/10/2026 · Căn cứ: `docs/data/sample_review.md`, `docs/plans/02-spike-notes.md` (số liệu đo trên sample thật).
Quy trình thực tế: code làm trước theo từng đề xuất, duyệt sau. Spec gốc đã được đồng bộ với **code hiện có** (v1.4); những chỗ code đi theo đề xuất chưa duyệt được đánh dấu "chờ Trung duyệt" trong spec gốc. Các thay đổi khác (bảng lớn, `--classification`, store tự embed) đã vào spec gốc, xem `02-ingest-index-spec.md` §9.

## Tình trạng các đề xuất

| # | Đề xuất | Code | Spec gốc | Việc cần Trung |
|---|---|---|---|---|
| 1 | FR-02 đánh giá extractor theo từng trang | **Không còn cần** (xem dưới) | Không đổi | Đóng đề xuất |
| 2 | FR-02b kiểm text layer hỏng | Đã làm **dạng cảnh báo**, không tự OCR lại | Đã thêm FR-02b, AC-18 | Duyệt cách làm và ngưỡng 0,05 |
| 3 | AC-02: đổi tiêu chí cho XLSX là biểu mẫu | Test đang kiểm theo phương án A | **AC-02 chưa đổi** | Chọn phương án A hoặc B |
| 4 | AC-03: dùng DOC-04 làm ca OCR thật | Đã làm, test pass trên file thật | AC-03 đã đổi | Xác nhận |
| 5 | Docling là extractor chính, bỏ Surya đứng riêng | Đã làm | FR-02 và §2 đã đổi | Duyệt (DoD S1-1 còn ghi "mmore CPU + Docling/Surya") |

## Đề xuất 1 — FR-02: đánh giá theo từng trang — **không còn cần**

**Vấn đề ban đầu (đo được).** `6-7 NASWEB Supplier-Label-Tech Spec.pdf` (DOC-04) có 9 trang, trung bình 807 ký tự/trang nhưng trang 3 và 6 chỉ có 33–34 ký tự (bản vẽ nhãn, mã QR nằm trong ảnh). Quy tắc "trung bình cả file < 50" sẽ bỏ mất 2 trang này.

**Kết quả sau khi đổi sang Docling (đề xuất 5).** Docling mặc định đã OCR vùng ảnh. Chữ trên trang 3 vẫn bị mất, nhưng do `docling_to_raw` bỏ nhãn `picture` chứ không phải do chọn extractor. Đã sửa: chữ OCR trong hình thành chunk `kind=drawing_note`. Test thật trên DOC-04 trang 3 thấy `TN057763-7131`. Vì vậy không cần chọn extractor theo trang trên đường Docling. Phần còn lại (Docling lỗi, rơi về mmore fast, mất chữ trong ảnh) đã được chấp nhận và đánh dấu `metadata.degraded = true`.

## Đề xuất 2 — FR-02b: kiểm tra chất lượng text layer — đã làm dạng cảnh báo

**Vấn đề (đo bằng `pypdf`).** DOC-01 có 1152 ký tự/trang nhưng text layer mã hóa sai (0% ký tự Nhật, trang 1 bắt đầu bằng `ʵʵ σϯιʔςΫχΧϧϨϏϡʔ...`). Đếm ký tự không phát hiện được.

**Kết quả đo thêm.** mmore fast, pdfium và Docling đều đọc đúng DOC-01 (6.800 ký tự Nhật, 5 ký tự lạ); chỉ `pypdf` ra chữ rác. Nên DOC-01 không còn là REDO và FR-02b hạ xuống mức Should.

**Cách đã làm (khác đề xuất gốc).** `capture/ingest/quality.py`: trang có > `KNOWHOW_TEXT_QUALITY_MAX_ODD_RATIO` (mặc định 0,05) chữ IPA-mở-rộng/Hy Lạp trên tổng chữ cái (tối thiểu 20 chữ cái) bị **cảnh báo** trong dòng log FR-08. Trang vẫn được chunk, không tự OCR lại. Đo trên 4 tài liệu thật, trang xấu nhất 1,0% (bài báo có công thức) nên không báo nhầm.

**Hạn chế.** Chưa có ca dương thật để kiểm: chưa gặp PDF nào mà extractor đang dùng thực sự đọc ra rác. Test dùng chuỗi rác trích từ review. Bộ chữ chỉ nhắm vào kiểu rác của DOC-01.

## Đề xuất 3 — AC-02: không kiểm được trên XLSX mẫu hiện có — **chờ chọn**

**Vấn đề (đo được).** `sps_form_12_1_14.xlsx` (DOC-05) là **biểu mẫu**: 3 sheet, 0 Excel table, 97 ô gộp mỗi sheet biểu mẫu, dữ liệu là cặp `nhãn: giá trị` rải rác (`DENSO PART NUMBER: AA123456-7890`). Không có bảng chữ nhật nên "giữ đủ số hàng/cột" không xác định được.

**Phương án A (khuyến nghị, test đang theo phương án này):**
```diff
- **AC-02** Bảng trong XLSX mẫu → chunk `kind=table` giữ đủ số hàng/cột.
+ **AC-02** XLSX mẫu (`sps_form_12_1_14.xlsx`) → mọi chunk là `kind=table` có hàng phân cách; các giá trị nhãn–giá trị của file gốc (VD `AA123456-7890`) có trong text chunk. Bảng chữ nhật giữ đủ số hàng/cột — kiểm bằng fixture XLSX nhỏ tự tạo.
```
**Phương án B:** bổ sung một XLSX công khai có bảng chữ nhật vào `data/samples/docs/`; phải tìm nguồn và xác nhận quyền phát hành lại.

**Còn thiếu cho phương án A:** fixture XLSX có bảng chữ nhật thật chưa có. Test hiện tại chỉ kiểm giá trị, chưa kiểm số hàng/cột.

## Đề xuất 4 — AC-03: dùng DOC-04 làm ca OCR thật — đã làm

AC-03 trong spec gốc: "Trang ảnh/scan → `extractor = docling` và có text từ OCR", bộ kiểm DOC-04 (trang 3, 6) và `packing_sop_scan.pdf`. Test `tests/capture/ingest/test_samples.py` pass trên file thật (bật bằng `KNOWHOW_RUN_SAMPLE_TESTS=1`). Lưu ý: kiểm trang 3 (`TN057763-7131`), chưa kiểm nội dung trang 6.

Bản scan giả: OCR tiếng Việt sai dấu nhưng giữ đúng `PACK01`; đã thử 3 cấu hình khác và giữ mặc định (`02-spike-notes.md`).

## Đề xuất 5 — Docling là extractor chính — đã làm, chờ duyệt

**Vấn đề (đo được, CPU).** mmore fast làm mất cấu trúc bảng PDF và trả XLSX dạng dump pandas, không đạt FR-03/AC-02. mmore đầy đủ (marker + Surya) đạt nhưng cần 3,3 GB model và ~100 s/file. Docling đạt bảng PDF, OCR vùng ảnh và XLSX (0,6 s) với 529 MB model. Surya đã nằm trong `mmore[process]`.

```diff
- **FR-02** Chọn extractor: thử mmore; nếu text trích được < 50 ký tự/trang trung bình → coi là scan → Docling OCR; nếu Docling lỗi → Surya.
+ **FR-02** Extractor chính là Docling cho `.pdf .docx .xlsx .pptx`. Nếu Docling lỗi hoặc ra 0 khối: PDF chuyển sang mmore fast (chỉ text; `metadata.degraded = true`); file Office báo lỗi. Log lý do chuyển (FR-08).
- | Scan chất lượng thấp | Surya OCR | fallback 2, extra `ingest-ocr` |
+ | (bỏ) Surya đứng riêng | — | đã có trong mmore đầy đủ nếu sau này cần |
```
`DocumentChunk.extractor` vẫn cho phép `"mmore" | "docling" | "surya"`. Chi phí đổi: lệch chữ "mmore CPU" trong DoD S1-1.

## Câu hỏi cho Trung
1. Duyệt đề xuất 5 (Docling chính, mmore fast fallback, bỏ Surya đứng riêng) và sửa chữ DoD S1-1?
2. Đề xuất 3: phương án A hay B? Nếu A, có cần fixture XLSX có bảng chữ nhật không?
3. Đề xuất 2: chấp nhận FR-02b ở dạng cảnh báo (không tự OCR lại) với ngưỡng 0,05?
4. Đề xuất 1 đóng lại; đề xuất 4 xác nhận.
