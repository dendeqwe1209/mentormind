# Kết quả VLM trên video demo LASI — 28/9/2026

Ảnh chụp kết quả để cả đội xem được mà không cần chạy lại. Video: `data/video/LASI Success Case - Food Industry
(Asian Alliance Internation Co.,Ltd.) [m4icg6FgTBU].mkv` (public, 193.8 s, qua Git LFS), `video_id = VID-96bd368c7e84`.
Ground truth: `data/video/groundtruth.json` (27 bước, **draft**, chờ Đạt duyệt). Model: **Qwen3-VL-8B-Instruct** (thêm một lần chạy **Qwen3-VL-32B-Instruct** để so).

Chỉ có file text (JSON/CSV/MD). Khung hình, clip, model và audit **không** commit: `data/work/` vẫn bị gitignore
(spec 01 FR-06), vì khi chạy trên dữ liệu nhà máy thì dữ liệu mật cũng rơi vào đó. Mọi thứ ở đây là `public`.

## Tóm tắt

| Kết luận | Số liệu |
|---|---|
| Tự host và cloud (cùng model) mô tả **giống nhau về nghĩa khoảng 78%** | soft F1 (bge-m3) 0.78; mô tả cảnh 0.86 |
| Thêm trường `actor` (prompt v1.6) cải thiện rõ | recall ngữ nghĩa 0.19 → 0.33; precision 0.29 → 0.45; `actor_accuracy` 0.80 |
| Lượt B (chạy lượt A 2 lần) bỏ bước bịa | precision ngữ nghĩa 0.25 → 0.42 (pipeline `describe`, prompt v1.5) |
| **Qwen3-VL-32B** không tìm đúng thêm bước nào so với 8B, chỉ phủ thời gian rộng hơn và tách bước vụn hơn, lại chậm hơn khoảng 4 lần | recall ngữ nghĩa 0.33 = 0.33; precision 0.45 (8B) → 0.33 (32B); 53 s → 221 s |
| Điểm yếu còn lại: model 8B dùng từ chung ("sản phẩm/hộp"), bỏ sót thao tác tay tinh, mốc giờ dồn về biên đoạn 10 s | recall theo thời gian 0.41–0.56 |

Một lần chạy mỗi cấu hình (`temperature=0.2`): chênh lệch ±0.05 chưa có ý nghĩa thống kê.

## Các lần chạy (`runs/`)

| Thư mục | Máy / nơi chạy | Prompt lượt A | Lệnh |
|---|---|---|---|
| `sweep-a5000-promptv1.5/fps{1,2,8}` | 1 × RTX A5000, vLLM 0.16 | v1.5 | `knowhow vlm sweep --fps 1,2,4,8` |
| `sweep-mi250-promptv1.5/fps4` | 1 GCD MI250 (GCD 1), vLLM 0.23 ROCm | v1.5 | `knowhow vlm sweep --fps 4` |
| `sweep-mi250-promptv1.6-actor/fps4` | như trên | v1.6 (`actor`, tên bước không chủ thể) | `knowhow vlm sweep --fps 4` |
| `sweep-cloud-dashscope-promptv1.5/fps4` | Alibaba Model Studio Singapore (`qwen_api`), **chạy 1 lần** | v1.5 | `knowhow vlm sweep --provider qwen_api --fps 4` |
| `sweep-mi250-32b-promptv1.6-actor/fps4` | **Qwen3-VL-32B-Instruct**, 2 GCD MI250 (GCD 2+3, tensor parallel 2), vLLM 0.23 ROCm | v1.6 | `KNOWHOW_VLM_PROVIDER=openai_compatible KNOWHOW_VLM_BASE_URL=http://127.0.0.1:8101/v1 KNOWHOW_VLM_MODEL=Qwen/Qwen3-VL-32B-Instruct KNOWHOW_VLM_JSON_MODE=json_schema knowhow vlm sweep --fps 4` |
| `describe-mi250-promptv1.5` | MI250, VLM + LLM lượt C đều tự host | v1.5 | `knowhow vlm describe --video ...` |
| `describe-mi250-promptv1.6-actor` | như trên | v1.6 | `knowhow vlm describe --video ...` |

Mọi lệnh có `--classification public`. fps 4 của A5000 bị lần chạy MI250 ghi đè nên không còn file chi tiết; số của
nó vẫn nằm trong `sweep/lasi_local_openai.csv`.

Trong mỗi thư mục sweep `fpsN/`:
- `pass_a/<segment>.json`: prompt, câu trả lời gốc, token, mốc giờ từng khung; thêm `*.repair.json` nếu phải sửa JSON.
- `predictions.json`: các bước với giờ tuyệt đối.
- `profiles_draft.json`: WorkProfile nháp, hợp lệ contract.
- `failed_segments.json`: đoạn trả JSON hỏng cả 2 lần (chỉ có ở bản cloud: DashScope `json_object` không ép schema).

Trong mỗi thư mục describe: `pass_a/` (lần 1), `pass_b/pass_a/` (lần 2), `pass_c.json` (prompt + câu trả lời + báo cáo
gộp), `predictions.json`, `profiles.json`. **WorkProfile cuối cùng** (bản mới nhất, v1.6): `profiles.json` ở thư mục này.

## Bảng sweep (`sweep/`)

A5000, prompt v1.5 (`lasi_local_openai.md`):

| fps | recall | recall (chính) | recall (chỉ thời gian) | precision | bước | token | độ trễ (s) |
|---|---|---|---|---|---|---|---|
| 1 | 0.07 | 0.12 | 0.26 | 0.40 | 5 | 26 396 | 39.6 |
| 2 | 0.07 | 0.12 | 0.33 | 0.18 | 11 | 37 943 | 55.3 |
| 4 | 0.07 | 0.12 | 0.41 | 0.11 | 18 | 53 417 | 78.1 |
| 8 | 0.11 | 0.12 | 0.44 | 0.19 | 16 | 72 128 | 78.5 |

fps 4 trên MI250 và cloud:

| Cấu hình | recall | recall (chính) | recall (chỉ thời gian) | precision | actor | bước | token | độ trễ (s) |
|---|---|---|---|---|---|---|---|---|
| MI250, v1.5 | 0.04 | 0.06 | 0.41 | 0.06 | — | 17 | 53 325 | 48.9 |
| MI250, v1.6 + `actor` | 0.11 | 0.19 | 0.56 | 0.15 | 0.80 | 20 | 55 782 | 52.8 |
| Cloud DashScope, v1.5 | 0.00 | 0.00 | 0.00 | 0.00 | — | 0 | 74 570 | 41.6 |
| **32B**, MI250 2 GCD, v1.6 + `actor` | 0.07 | 0.12 | 0.78 | 0.05 | 0.86 | 39 | 58 746 | 221.1 |

`recall`/`precision` dùng luật chữ của spec 04 (`token_set_ratio ≥ 70` + trùng giờ), rất khắt khe với tiếng Việt tự do.
Cloud ra 0 bước vì 6/20 đoạn bị loại do sai schema (`objects` là chuỗi); code đã sửa sau đó. So sánh dưới đây đọc lại
câu trả lời đã lưu bằng luật chịu lỗi, nên cloud vẫn được chấm công bằng.

## So sánh ngữ nghĩa (`compare/`)

bge-m3 cosine; ngưỡng 0.65 ≈ "cùng hành động, khác từ", 0.75 ≈ "gần như cùng câu" (`summary_t065.json`, `summary_t075.json`).
`compare_segments.csv`: mỗi đoạn một dòng, gồm scene + các bước của hai bên (có `(actor)`); `compare_steps.csv`: từng cặp bước.

| So với ground truth (≥ 0.65) | Tự host v1.5 | Cloud v1.5 | Tự host v1.6 + `actor` |
|---|---|---|---|
| recall ngữ nghĩa | 0.19 | 0.15 | **0.33** |
| precision ngữ nghĩa | 0.29 | 0.44 | **0.45** |
| số bước | 17 | 9 | 20 |
| token | 53.3k | 74.6k | 55.8k |

Chạy lại so sánh: `python compare/selfhost-vs-cloud/compare.py <repo> 0.65 <out_dir> A=<run_dir> B=<run_dir>`
(cần `sentence-transformers` + `BAAI/bge-m3`; script đọc thư mục `data/work/...` của máy đã chạy).

## Qwen3-VL-8B so với 32B (`compare/8b-vs-32b/`)

Cùng video, cùng 20 đoạn 10 s, fps 4, cùng prompt v1.6 (`actor`), cùng `json_schema`. 32B BF16 nặng 66.7 GB, lớn hơn một
GCD 64 GB, nên chạy tensor parallel 2 trên 2 GCD (`run-32b.sh`, thí nghiệm ngoài luật 1 GPU của `vlm_server`).

| So với ground truth (bge-m3 ≥ 0.65) | 8B, 1 GCD | 32B, 2 GCD |
|---|---|---|
| số bước | 20 | 39 |
| recall ngữ nghĩa | **0.33** | **0.33** |
| precision ngữ nghĩa | **0.45** | 0.33 |
| recall theo thời gian | 0.63 | **0.81** |
| `actor_accuracy` (sweep) | 0.80 | **0.86** |
| token vào | 55.8k | 58.7k |
| thời gian GPU | **52.8 s** | 221.1 s |

Hai model giống nhau về nghĩa ở mức soft F1 0.69; mô tả cảnh giống nhau 0.79.

- 32B **nhìn kỹ hơn**: phủ thời gian rộng hơn, mốc giờ bám thao tác thay vì dồn về biên đoạn 10 s. Ví dụ đoạn 80–90 s: 8B
  ghi `90.0–90.0`, 32B ghi `83.0–88.5`, ground truth là 84–87 s. `actor` cũng đúng hơn.
- 32B **tách vụn**: một lần robot gắp thành 4 bước ("di chuyển cánh tay", "gắp", "đưa tới hộp", "rút tay"), vượt quy tắc
  "thao tác lặp lại ghi một bước" của prompt. Số bước đúng không tăng, nên precision giảm.
- **Đề xuất cho MVP:** giữ 8B trên 1 GCD (ngang số bước đúng, precision cao hơn, nhanh hơn khoảng 4 lần, tốn nửa GPU). 32B
  đáng cân nhắc khi cần mốc giờ chính xác cho clip bằng chứng; khi đó nên siết prompt về độ chi tiết của bước. Một video,
  một lần chạy: cần thêm video trước khi chốt.
