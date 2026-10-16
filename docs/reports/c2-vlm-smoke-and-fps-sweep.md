# C2 — Smoke test VLM và kế hoạch quét fps

**Task:** C2 (Phúc) · **Reviewer:** Trung · **Ngày chạy:** 28/9/2026 · **Spec:** 04 §4, §6

## 1. Tóm tắt

| Câu hỏi của C2 | Trả lời |
|---|---|
| Gọi VLM trên clip public, ra JSON đúng schema? | **Có.** Qwen3-VL-8B-Instruct tự host (1 × RTX A5000) trả JSON đúng schema ở mọi lần gọi: 0 đoạn lỗi JSON trên 80 lần gọi lượt A, nhờ `response_format=json_schema` (guided decoding của vLLM) và lớp parse chịu lỗi |
| Cách quét fps 1/2/4/8 | `knowhow vlm sweep` (spec 04 §6): cắt video thành đoạn, chạy lượt A ở từng fps, so với ground truth gán tay, xuất CSV + bảng markdown |
| Chi phí token | Ở 4 fps: **khoảng 16k token vào và 0.8k token ra cho mỗi phút video**, tức khoảng $0.002/phút trên OpenRouter (route Alibaba) và khoảng $0.0035/phút trên SiliconFlow/DashScope. Tự host thì không tốn tiền, mất khoảng 24 s GPU cho mỗi phút video |
| Chốt fps | **Mặc định 4 fps, 8 fps cho đoạn chuyển động nhanh, 2 fps cho đoạn tĩnh** (spec 04 FR-02b giữ nguyên). 8 fps tốn thêm 37% token mà độ phủ chỉ tăng 3 điểm |

## 2. Smoke test

| Kiểm tra | Kết quả |
|---|---|
| Clip tổng hợp 8 khung (hình vuông đỏ trượt vào hộp; muốn trả lời đúng phải hiểu **thứ tự** khung) | PASS: 1.0k token vào, 1.6 s |
| Clip tổng hợp 48 khung (trần của spec 04) | PASS: 5.5k token vào, 2.9–3.8 s |
| Clip thật 12 s (*Master Hands*, 1936, public domain: công nhân lắp chi tiết vào block máy) | 23 khung sau khi bỏ trùng, 2.7k token vào; mô tả tổng quan đúng |
| Container `mentormind` → container `vlm-server` (1 GPU, autostart) | PASS với 48 khung (task D3) |

Lệnh: `uv run knowhow vlm ping [--frames 48]`, `uv run knowhow vlm ping --video <clip> --classification public`.

## 3. Quét fps trên video demo

**Thiết lập**
- Video *LASI Success Case – Food Industry* (YouTube `m4icg6FgTBU`, public), 193.8 s, 1080p.
  Nội dung: đóng thùng cốc thức ăn thú cưng, gồm robot SCARA DENSO, công nhân đậy nắp và dồn cốc, xen cảnh phỏng vấn.
- Ground truth `data/video/groundtruth.json`: 50 cảnh phủ kín video, 27 bước (17 bước thuộc công đoạn chính),
  gán tay từ khung hình, **không** lấy từ output VLM.
- Video được cắt thành 20 đoạn 10 s (fallback `fixed_window` của spec 03, vì bộ cắt đoạn theo cảnh chưa có).
  Mỗi lời gọi tối đa 48 khung, ảnh 448 px, `temperature=0.2`, `presence_penalty=1.5`.
- Model: Qwen3-VL-8B-Instruct BF16 trên vLLM 0.16, 1 × RTX A5000.

**Phát hiện 1 — prompt lượt A v1.0 trả rỗng.** Prompt nguyên văn của spec 04 v1.0 trả `{"steps": []}` cho
**cả 20 đoạn ở cả 4 mức fps**, kể cả khi bỏ `json_schema`, bỏ câu "Không có thao tác nào → trả rỗng" hoặc bỏ
dòng JSON mẫu. Chỉ khi bắt model **mô tả cảnh (`scene`) trước rồi mới trích bước** thì model mới ra bước.
Prompt v1.5 đã áp dụng cách này (spec 04 §4).

**Kết quả với prompt v1.5**

| fps | fps thực | recall | recall (công đoạn chính) | recall (chỉ thời gian) | precision | order | bước dự đoán | token vào | token ra | GPU (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | 0.07 | 0.12 | 0.26 | 0.40 | 1.00 | 5 | 25,023 | 1,373 | 39.6 |
| 2 | 2 | 0.07 | 0.12 | 0.33 | 0.18 | 1.00 | 11 | 36,090 | 1,853 | 55.3 |
| **4** | 4 | 0.07 | 0.12 | **0.41** | 0.11 | 1.00 | 18 | 50,846 | 2,571 | 78.1 |
| 8 | 7.94 | 0.11 | 0.12 | 0.44 | 0.19 | 1.00 | 16 | 69,775 | 2,353 | 78.5 |

- `recall`/`precision`: luật của spec (`token_set_ratio ≥ 70` **và** trùng thời gian).
- `recall (chỉ thời gian)`: tỷ lệ bước truth có ít nhất một bước dự đoán trùng thời gian, bất kể câu chữ.
- Không đoạn nào lỗi JSON.

**Đọc kết quả**
1. **Model thấy đúng thao tác nhưng chấm theo chữ thì trượt.** Ví dụ ở 4 fps, model ghi "Robot đặt linh kiện
   vào hộp" (75.0–79.8 s), truth ghi "Đặt cụm cốc nắp đỏ vào thùng carton" (72.6–79.7 s): đúng thao tác, đúng
   thời gian, nhưng `token_set_ratio` thấp. Model dùng từ chung ("sản phẩm", "linh kiện", "hộp") vì prompt
   gợi ý như vậy. Vì thế `recall` 0.07–0.11 **đánh giá thấp** chất lượng thật; `recall (chỉ thời gian)` 0.26–0.44
   phản ánh độ phủ sát hơn.
2. **Mốc thời gian hay dồn về biên đoạn** (vd. `90.0–90.0`): model ước `t_*_rel` lệch hoặc vượt độ dài đoạn,
   code phải kẹp lại. Đoạn 10 s cố định cắt ngang nhiều cảnh (video demo đổi cảnh 2–7 s một lần) nên càng khó.
3. **Phỏng vấn và logo**: phần lớn trả `steps` rỗng đúng như mong đợi, và `scene` mô tả đúng ("người phụ nữ đeo khẩu trang đang nói chuyện").
4. **fps**: độ phủ tăng đều từ 1 lên 4 fps (0.26 → 0.41). Lên 8 fps chỉ thêm 0.03 nhưng tốn thêm 37% token vào.

## 4. Chi phí token (Qwen3-VL-8B-Instruct, giá kiểm tra 28/9/2026)

**Chi phí một lần chạy lượt A cho cả video 3:14 (USD)**

| fps | OpenRouter (route Alibaba) $0.117/$0.455 | SiliconFlow $0.18/$0.68 | DashScope Singapore $0.18/$0.70 | OpenRouter (route Parasail) $0.25/$0.75 | Tự host |
|---|---|---|---|---|---|
| 1 | 0.0036 | 0.0054 | 0.0055 | 0.0073 | 0 |
| 2 | 0.0051 | 0.0078 | 0.0078 | 0.0104 | 0 |
| 4 | 0.0071 | 0.0109 | 0.0110 | 0.0146 | 0 |
| 8 | 0.0092 | 0.0142 | 0.0142 | 0.0192 | 0 |

**Mỗi phút video ở 4 fps:** 15.7k token vào và 0.8k token ra (khoảng 2.5k token vào cho mỗi đoạn 10 s).

**Ước tính cho luồng thật của spec 04:** lượt A chạy 2 lần cho lượt B tự nhất quán, cộng lượt C (text, nhỏ).
Một video công đoạn 5 phút (architecture §3) ở 4 fps tốn khoảng 160k token vào và 8k token ra:
- OpenRouter (route Alibaba): khoảng $0.022 mỗi video;
- DashScope hoặc SiliconFlow: khoảng $0.034 mỗi video.

| Nguồn miễn phí | Đủ cho |
|---|---|
| DashScope Singapore: 1M token/model trong 90 ngày (**`qwen3-vl-8b-instruct` ngừng ngày 10/10**) | khoảng 19 lần chạy video demo ở 4 fps, hoặc khoảng 6 video 5 phút theo luồng đầy đủ |
| SiliconFlow: $1 credit khi đăng ký | khoảng 90 lần chạy video demo ở 4 fps, hoặc khoảng 30 video 5 phút |
| Tự host (A5000) | Không giới hạn; khoảng 24 s GPU mỗi phút video ở 4 fps. Dữ liệu `factory_confidential` chỉ được chạy theo đường này |

## 5. Kế hoạch đã chốt

1. **fps**: giữ đúng spec 04 FR-02b, mặc định `KNOWHOW_VLM_FPS=4`, `motion_score ≥ 0.6` → 8 fps, `< 0.3` → 2 fps, tối đa 48 khung/lời gọi.
   Chạy lại sweep khi có bộ cắt đoạn theo cảnh của spec 03 để chốt lần cuối.
2. **Quét lại khi có key cloud**: cùng lệnh, chỉ đổi provider (`--provider qwen_api|openrouter|siliconflow`)
   để so chất lượng và độ trễ giữa tự host và cloud (video demo là `public` nên được phép gửi đi; khuôn mặt tự
   động được làm mờ).
3. **Đề xuất sửa đánh giá** (cần Đạt/Trung đồng ý, sẽ đưa vào spec 04 §6 / spec 09):
   - Thêm chỉ số khớp **ngữ nghĩa** (embedding bge-m3, cosine ≥ ngưỡng) bên cạnh `token_set_ratio`.
   - Hoặc viết ground truth theo từ vựng trung tính hơn ("sản phẩm/hộp").
4. **Đề xuất cải thiện mốc thời gian**: ghi nhãn thời gian ngay trước từng ảnh (`t=2.5s`, xen giữa các ảnh)
   thay cho một danh sách; về lâu dài gửi dạng `video` để Qwen3-VL dùng mã hóa thời gian gốc.
5. **Cắt đoạn theo cảnh** (spec 03 T03-2): đoạn 10 s cố định trộn nhiều cảnh, làm giảm cả recall lẫn độ chính xác thời gian.

## 6. Chạy lại

```bash
make vlm-server                                   # hoặc: VLM_SERVER_AUTOSTART=true docker compose up -d
KNOWHOW_VLM_EXTRA_BODY='{"presence_penalty": 1.5}' uv run knowhow vlm sweep \
  --video "data/video/LASI Success Case - Food Industry (Asian Alliance Internation Co.,Ltd.) [m4icg6FgTBU].mkv" \
  --truth data/video/groundtruth.json --fps 1,2,4,8 \
  --out data/work/sweep/lasi_local_openai.csv --classification public --process-id PACK01
```
Chi tiết từng fps (raw answer, `predictions.json`, `profiles_draft.json`):
`data/work/vlm/VID-96bd368c7e84/sweep-local_openai/fps<N>/`.
