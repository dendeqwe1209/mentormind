# Review data sample — tài liệu (S0-5, bản nháp 1)

Ngày: 29/9/2026 · Người review: Việt Hoàng (số liệu đo bởi script, xem "Cách đo") · Spec: `docs/plans/02-ingest-index-spec.md` §3
Phạm vi: 5 tài liệu trong `docs/data/MentorMind_Sample_Data.xlsx` (bảng kê đầy đủ) + `data/demo/packing/packing_sop.pdf` + 1 file chưa có trong bảng kê (SQAM 2024). **Video (VID-01..05) chưa review** — chờ xác nhận S0-5 có gồm video không.

## Kết luận

| ID | File | Kết luận | Tóm tắt |
|---|---|---|---|
| DOC-01 | `09-1-doc-dissertation14-id-ja.pdf` | **ACCEPT** (cập nhật 3/10) | Số đo `pypdf` báo chữ Nhật bị mã hóa sai, nhưng spike T02-0 (`02-spike-notes.md`) cho thấy mmore fast đọc đúng. Không còn là REDO; ca test tiếng Nhật. Chưa chạy Docling trên file này. |
| DOC-02 | `24-doc-15-paper-10.pdf` | **ACCEPT** | Tiếng Nhật, text layer đọc được. Kiểm thử ingest tiếng Nhật. |
| DOC-03 | `NA Final SQAM 20220627.pdf` | **ACCEPT** (đã nằm sẵn trong repo, nhãn `public` theo bảng kê; ghi chú: bản mới hơn của DENSO có thể cần quyền tải) | 84 trang, text tốt. Ứng viên PDF text cho AC-01. |
| DOC-04 | `6-7 NASWEB Supplier-Label-Tech Spec.pdf` | **ACCEPT** | File đã có ở `data/` (tên khác bảng kê: dấu cách thay dấu gạch). 9 trang, **2 trang chỉ có ảnh** (3, 6) → ca test OCR theo trang rất tốt. |
| (chưa có ID) | `2024 NA DENSO SQAM Signed.pdf` | **REDO** | Đọc được tốt (106 trang, 259 chunk) nhưng **không có nhãn rõ**: không nằm trong `MentorMind_Sample_Data.xlsx`, chưa có URL nguồn. Theo spec §3.2, không có nhãn rõ → REDO. **Việc cần làm:** (a) ghi URL nguồn và nhãn vào bảng kê rồi mới dùng; hoặc (b) xóa khỏi `data/`. Trong lúc chờ: giữ ngoài repo, không commit, không ingest vào DB dùng chung. |
| DOC-05 | `sps_form_12_1_14.xlsx` | **ACCEPT** (điều kiện: sửa AC-02) | File đã có ở `data/`. Mở được, 3 sheet, không cần OCR. Nhưng là **biểu mẫu**, không phải bảng chữ nhật (xem phát hiện 3). |
| PACK01 | `data/demo/packing/packing_sop.pdf` | **ACCEPT** | `synthetic`, text sạch, có bản gốc `.md` để đối chiếu. Nguồn tạo bản scan giả cho AC-03. |

## Chi tiết đã đo

| File | Trang | Ký tự/trang (TB · min · max) | Trang < 50 ký tự | Ảnh nhúng | Mã hóa | Ngôn ngữ | Nhãn |
|---|---|---|---|---|---|---|---|
| DOC-01 | 9 | 1152 · 785 · 1614 | 0 | 33 | **Sai** (0% ký tự Nhật, có ký tự Latin mở rộng/Hy Lạp) | Nhật | `public` |
| DOC-02 | 16 | 1855 · 687 · 4254 | 0 | 25 | Đúng (trang 9: 74% ký tự Nhật) | Nhật | `public` |
| DOC-03 | 84 | 1870 · 133 · 3728 | 0 | 135 | Đúng | Anh | `public` |
| PACK01 | 3 | 1685 · 575 · 2344 | 0 | 0 | Đúng | Việt | `synthetic` |
| DOC-04 | 9 | 807 · 33 · 1979 | **2** (trang 3, 6) | 8 | Đúng | Anh | `public` |
| SQAM 2024 | 106 | 2454 · 202 · 4998 | 0 | 155 | Đúng | Anh | chưa có nhãn |
| DOC-05 | 3 sheet | xem "Chi tiết DOC-05" | — | 0 | Đúng (XLSX native) | Anh | `public` |

Không file nào bị mã hóa mật khẩu. Các trang ít chữ nhất của DOC-03: trang 67 (133 ký tự), 15, 45, 3, 78 — nhiều khả năng là trang sơ đồ/biểu mẫu, cần xem tay.

## Phát hiện quan trọng

**1. Ngưỡng `< 50 ký tự/trang` (spec 02 FR-02) không phát hiện được DOC-01.** File này trung bình 1152 ký tự/trang nên lọt qua ngưỡng và bị coi là "có text", trong khi nội dung là rác (ví dụ trang 1 bắt đầu bằng `ʵʵ σϯιʔςΫχΧϧϨϏϡʔ...`). Chunk sinh ra sẽ làm hỏng embed và retrieval mà không có cảnh báo.
- Lưu ý: số liệu trên đo bằng `pypdf`. mmore có thể dùng thư viện khác và đọc đúng. **Chưa xác minh** — làm ở T02-0.
- Đề xuất bổ sung FR-02: thêm kiểm tra chất lượng text (tỉ lệ ký tự bất thường, hoặc tỉ lệ ký tự thuộc bộ chữ kỳ vọng) ngoài ngưỡng số ký tự; nếu không đạt thì coi như scan. Chờ bạn duyệt trước khi sửa spec (theo CLAUDE.md).

**2. Không có file scan thật nào.** Cả 5 tài liệu ghi "PDF text/XLSX". Muốn test AC-03 phải tạo bản scan giả từ `packing_sop.pdf` (chưa làm). DOC-01 có thể dùng như một ca kiểm thử OCR thật nếu xác nhận text layer hỏng.

**3. DOC-05 là biểu mẫu, không phải bảng dữ liệu.** Tải tự động bị HTTP 403 nên bạn tải tay; file đã có ở `data/sps_form_12_1_14.xlsx` (183 KB, hợp lệ). Cấu trúc đo được:

| Sheet | Vùng | Ô có giá trị | Ô gộp | Excel table | Công thức | Ảnh |
|---|---|---|---|---|---|---|
| Guidelines | A1:I27 | 35 | 0 | 0 | 0 | 0 |
| Completed Example | A1:Y58 | 131 | 97 | 0 | 10 | 0 |
| Blank Spec | A1:Y58 | 89 | 97 | 0 | 7 | 0 |

- `Guidelines`: 11 quy tắc dạng văn bản, không có bảng.
- `Completed Example` và `Blank Spec`: cùng một biểu mẫu Supplier Packaging Specification, gồm các khối "PART INFORMATION", "PACKAGING DATA", "DIMENSION / WEIGHT / QUANTITY". Bố cục dựa vào 97 ô gộp; các cặp `nhãn: giá trị` nằm rải rác, ví dụ `DENSO PART NUMBER: AA123456-7890`.
- `Blank Spec` gần như trống (chỉ có nhãn) → chunk sinh ra gần như không có nội dung; nên loại khỏi bộ test AC-01 hoặc chấp nhận ít chunk.
- **Hệ quả cho AC-02** ("chunk `kind=table` giữ đủ số hàng/cột"): file này không có bảng chữ nhật, nên "đủ số hàng/cột" không xác định rõ. Cần đổi AC-02 thành một tiêu chí kiểm được, ví dụ "mọi cặp nhãn–giá trị của `Completed Example` xuất hiện trong text chunk", hoặc thêm một XLSX có bảng thật vào bộ test. Chờ bạn/Trung chọn.

**4. Số bảng chưa đếm được.** `pypdf` không nhận diện bảng. Đếm bảng của DOC-03/DOC-04 phải chờ Docling/mmore (T02-0) hoặc xem tay. Đặc biệt DOC-03 là ứng viên bảng lớn cho AC-10.

**5. Python trên máy là 3.9.6, repo yêu cầu 3.11–3.12.** Cần `uv` (sẽ tự tải 3.11) trước khi chạy code của dự án. Script đo dùng venv riêng, không ảnh hưởng.

**6. Hai phát hiện mới từ DOC-04 và SQAM 2024.**
- **DOC-04 có trang chỉ chứa ảnh** (trang 3 = 33 ký tự, trang 6 = 34 ký tự): bản vẽ nhãn container và mã QR. Trung bình 807 ký tự/trang vượt ngưỡng 50 nên FR-02 (tính **trung bình cả file**) sẽ coi cả file là text và bỏ mất nội dung 2 trang ảnh. Đề xuất sửa FR-02: đánh giá **theo từng trang**, trang < 50 ký tự (hoặc text hỏng, xem phát hiện 1) được OCR riêng. Đây là đúng tình huống "bản vẽ có chú thích" của spec 02. Chờ bạn duyệt trước khi sửa spec.
- **SQAM 2024 là phiên bản khác của DOC-03, không phải bản trùng.** Kiểm bằng hash: không có file nào trong `data/` trùng byte. Nếu dự án chỉ cần một bản SQAM thì chọn bản nào cho bộ AC-01 và ghi nhãn `public` vào bảng kê. Bản 2024 mới hơn và dài hơn (106 trang), nhưng nhiều khả năng cần quyền tải/redistribute như ghi chú của DOC-03; chưa kiểm.

## Việc còn lại để hoàn tất S0-5
- [x] DOC-05 đã tải và đo (xem phát hiện 3).
- [ ] Chốt lại AC-02 (biểu mẫu không có bảng chữ nhật) và di chuyển file vào `data/samples/docs/` khi bộ AC-01 chốt.
- [ ] Không commit `docs/data/~$MentorMind_Sample_Data.xlsx` (file khóa tạm của Excel đang mở); nên thêm `~$*` vào `.gitignore`.
- [ ] Xem tay 5 trang ít chữ nhất của DOC-03 (67, 15, 45, 3, 78) và trang 3, 6 của DOC-04.
- [ ] Chốt SQAM 2024: thêm vào bảng kê (ID, nhãn) hay bỏ; chọn bản 2022 hay 2024 cho AC-01.
- [ ] Xác minh DOC-01 bằng mmore/Docling (T02-0): text layer có thực sự hỏng, hay chỉ `pypdf` đọc sai.
- [ ] Tạo bản scan giả `packing_sop_scan.pdf` (synthetic).
- [ ] Hỏi Đạt: được commit DOC-03 vào `data/samples/` không (ghi chú nguồn nói tải bản mới có thể cần quyền).
- [ ] Xác nhận với Đạt: S0-5 có gồm 5 video không.

## Cách đo
Script Python dùng `pypdf` 6.19 chạy trong venv riêng (không nằm trong repo); trang có `extract_text()` lỗi được tính là 0 ký tự. "Ảnh nhúng" là số ảnh `pypdf` liệt kê, không phải số trang scan. Tỉ lệ ký tự Nhật tính theo khối Unicode Hiragana/Katakana/CJK. Đây là số đo thô, chưa thay cho kiểm tra bằng mmore/Docling.

## Cập nhật 3/10
- Đã tạo `data/samples/docs/`: `packing_sop.pdf` (PDF text, `synthetic`), `packing_sop_scan.pdf` (scan giả sinh bởi `scripts/make_scan_sample.py`, `synthetic`), `sps_form_12_1_14.xlsx` (DOC-05, `public`). `packing_sop.pdf` thay tạm DOC-03 cho vai trò "PDF text" vì chưa có xác nhận quyền phát hành lại DOC-03.
- Ingest thật bằng Docling trên 3 file: 42 chunk, 0 lỗi (AC-01). Scan giả: 13 chunk `extractor=docling`, giữ được `PACK01`, nhưng OCR làm sai dấu tiếng Việt (VD "QUY TRINH THAO TÁC CHUN").

## Kết quả ingest thật bằng Docling (3/10, lần 2)
Số bảng và chất lượng đọc đo bằng `knowhow ingest run`, thay cho các ô "chưa đếm được" ở trên.

| ID | File | Trang | Chunk | Bảng (chunk / bảng gốc ≈) | Bảng bị tách (> 800 token) | Kết luận |
|---|---|---|---|---|---|---|
| DOC-01 | `09-1-doc-dissertation14-id-ja.pdf` | 9 | 72 | 2 / 2 | 0 | **ACCEPT** — 6.800 ký tự Nhật, chỉ 5 ký tự lạ; text đọc đúng, không cần ép OCR |
| DOC-02 | `24-doc-15-paper-10.pdf` | 16 | 75 | 0 / 0 | 0 | **ACCEPT** — 17.662 ký tự Nhật, 36 ký tự lạ; không có bảng |
| DOC-03 | `NA Final SQAM 20220627.pdf` | 84 | 229 | 34 / 27 | 9 | **ACCEPT** (điều kiện quyền phát hành lại) — ca bảng lớn cho AC-10 |
| (chưa có ID) | `2024 NA DENSO SQAM Signed.pdf` | 106 | 259 | 44 / 36 | 12 | **REDO** — thiếu nhãn/nguồn (xem trên) |

Hai lỗi lộ ra khi ingest SQAM 2024 (đã sửa, có test): Docling đặt tiêu đề bảng ("TABLE 1 - ...") trước dòng `|`, làm chunker tách bảng lớn ra phần không có hàng phân cách; và một chunk không hợp lệ làm dừng cả lô thay vì chỉ báo lỗi file đó.

## Chốt T02-7 (3/10)
1. **SQAM 2024** — áp quy tắc spec §3.2: thiếu nhãn/nguồn → **REDO** (hành động ở bảng kết luận). Không phải việc chặn phần còn lại.
2. **DOC-03** — đã được commit trong repo (`data/NA Final SQAM 20220627.pdf`) và bảng kê ghi `public`, nên không cần copy lại. `data/samples/docs/` dùng `packing_sop.pdf` (synthetic, nhanh, có đáp án `packing_sop_source.md`) làm PDF text; DOC-03 giữ ở `data/` cho ca bảng lớn (AC-10 trên file thật).
3. **Video VID-01..05** — ngoài phạm vi S0-5 (tiêu chí OCR/chất lượng scan): spec 03 gán dữ liệu video cho S0-7 (Đạt). Không review ở đây.
