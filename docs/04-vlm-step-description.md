# 04 — VLM Step Description

**Owner:** Phúc · **Tasks Excel:** S0-6, S1-3, S1-4, S2-6 (phần gắn reason)

## 1. Mục tiêu
Từ các `Segment` (spec 03) sinh ra danh sách `WorkProfile` ở trạng thái `draft`, hợp lệ theo contract, không chứa `reason` bịa. Đổi provider (API cloud ↔ self-host) chỉ bằng config.

## 2. Provider abstraction — `core.providers.vlm` (registry, theo pattern omnia)
Provider VLM nằm ở `core/providers/vlm/` (`base`, `models`, `registry`, `factory`, `catalog`, `backends/{openai_compat,fake}`), cạnh `core/providers/llm/` của spec 06; làm mờ mặt ở `core/guard/image/face_blur.py`. `processing/vlm/` chỉ còn nghiệp vụ: `pipeline` (`DescribePipeline`), `frames/` (`sampler`, `dedup`), `passes/` (`describe` = lượt A, `consistency` = lượt B, `merge` = lượt C, `reasons` = propose-reasons, `matching`, `postprocess`, `models`, `prompting`), `sweep/` (`truth`, `matching`, `metrics`, `runner`, `report`, `windows`), `cli/` (`diagnostics`, `describe`, `sweep`), `prompts/*.md`.

Phần dùng chung mọi loại provider nằm ở `core.providers` (spec 06 dùng lại cho LLM): `ProviderBase`,
`ProviderConfig`, `ProviderRegistry` (tên → class), `HttpClient` + retry (FR-07), bảng endpoint
OpenAI-compatible `OPENAI_COMPAT_ENDPOINTS`, `parse_json_object`.
```python
class VLMProvider(ProviderBase):          # ABC; subclass + @register_vlm("ten") là đủ
    name: str                             # tên registry, ghi vào model_info.provider
    model: str
    is_cloud: bool
    def generate(self, frames, prompt, *, classification, json_schema=None, system=None,
                 temperature=None, max_tokens=None) -> VLMResponse: ...   # text + usage + latency
    def generate_json(self, frames: list[Path], prompt: str, json_schema: dict, *,
                      classification, ...) -> dict: ...
    def _complete(self, images, prompt, ...) -> tuple[str, TokenUsage | None]: ...  # subclass viết

@register_vlm("local_openai", "qwen_api", "openrouter", "siliconflow", "openai_compatible")
class OpenAICompatVLM:   # 1 class cho mọi endpoint /chat/completions; vendor = 1 dòng trong bảng endpoint
@register_vlm("fake")
class FakeVLM:           # test: trả JSON cố định từ tests/fixtures/vlm/*.json, ghi lại mọi lời gọi
class GeminiVLM:         # Could — chỉ khi còn thời gian
```
- `generate` là template method: `DataGuard.check(classification, self)` chạy **trước** khi đọc file ảnh
  nên không provider nào quên được guard (AC-03).
- `is_cloud`: vendor cloud luôn `True`; `local_openai`/`openai_compatible` suy ra từ `base_url`
  (loopback, IP private, CGNAT/Tailscale, hostname LAN → local; còn lại → cloud) — AC-13.
  Ngoại lệ do người vận hành khai báo: hostname nằm trong `KNOWHOW_LOCAL_HOSTS` (danh sách JSON, khớp đúng cả tên,
  không phân biệt hoa thường, vd. `["abc.ngrok-free.dev"]` — tunnel tới máy tự host của chính đội) → local.
  Chỉ áp cho `local_openai`/`openai_compatible`; vendor cloud luôn cloud dù host có trong danh sách — AC-23.
- JSON mode theo endpoint (`KNOWHOW_VLM_JSON_MODE=auto`): `local_openai`, `openrouter` → `json_schema`;
  `qwen_api`, `siliconflow` → `json_object`. Luôn parse lại bằng `parse_json_object` (chịu được markdown fence).
- Key lấy theo tên biến của vendor (`OPENROUTER_API_KEY`...) từ môi trường rồi `.env`;
  `KNOWHOW_VLM_API_KEY` (khác rỗng) thắng tất cả. Hướng dẫn: `.secrets/README.md`.
- **Chế độ gửi mặc định: `frames`** — lấy mẫu khung hình từ `clip_path` theo `KNOWHOW_VLM_FPS`, gửi dạng nhiều ảnh base64 trong một message. Cách này chạy được trên mọi endpoint OpenAI-compatible, kể cả vLLM self-host với Qwen3-VL-8B sau này.
- Ảnh gửi đi resize cạnh dài 448px (ưu tiên độ dày thời gian hơn độ nét).
- **Lấy mẫu thích ứng** theo `Segment.motion_score` (spec 03): `≥ 0.6` → 8 fps; `< 0.3` → 2 fps; còn lại hoặc `None` → `KNOWHOW_VLM_FPS`.
- **Bỏ khung gần trùng**: perceptual hash (dHash 64-bit), bỏ khung có khoảng cách Hamming ≤ 4 so với khung giữ lại liền trước.
- **Trần số ảnh**: tối đa `KNOWHOW_VLM_MAX_FRAMES` (mặc định 48) ảnh/lời gọi; vượt trần → lấy mẫu đều lại cho vừa trần. `model_info.fps` ghi fps thực tế đã dùng.
- `get_vlm_provider(settings) -> VLMProvider` là factory duy nhất; code nghiệp vụ không import class cụ thể.
- Mọi lời gọi đi qua `DataGuard.check(classification, provider)` (spec 01, FR-09) **trước** khi đọc file.

## 3. Pipeline 3 lượt — `processing.vlm.pipeline.DescribePipeline(vlm, llm=...).run(segments, work_dir)` (`.profiles: list[WorkProfile]`)

**Lượt A — mô tả từng đoạn.** Với mỗi `Segment`, gọi VLM với prompt `prompts/pass_a_describe.md`, output theo schema:
```json
{"steps": [{"step": "str", "actor": "human|robot|machine|null", "hand_action": "str",
            "objects": ["str"], "key_point_observed": "str|null", "t_start_rel": 0.0,
            "t_end_rel": 0.0, "confidence": 0.0}]}
```
Một đoạn có thể có 0..n bước. `actor` = ai/cái gì làm bước đó: `human` (người: công nhân, kỹ sư), `robot` (robot có cánh tay), `machine` (máy tự động cố định), `null` = không rõ. Tên bước không ghi chủ thể. Từ ngoài enum ("công nhân", "robot SCARA") được chuẩn hóa; không nhận ra thì `null`, segment không bị loại.

**Thời gian của bước — hai cách, chọn bằng `KNOWHOW_VLM_STEP_TIMES`.** Model chỉ trỏ vào khoảnh khắc nhìn thấy thao tác (video LASI 8/10: đoạn dài 3–14 s nhưng bước có trung vị 1.4 s, 22/32 bước ≤ 2 s, vd. 116.9–117.0 s), nên trang duyệt chỉ phát được ~1 s mỗi bước và lượt B bỏ cặp bước cùng tên mà lệch giây. Ngay sau khi đọc câu trả lời của **một đoạn**, một `StepTimer` đặt thời gian tuyệt đối cho các bước của đoạn (`processing.vlm.passes.step_times`: lớp trừu tượng `StepTimer` với `name` và `place(steps, segment) -> [(step, t_start, t_end)]`, registry `STEP_TIMERS`, factory `get_step_timer(name)`). `describe_segments` và `DescribePipeline` nhận `step_timer` (mặc định `SegmentTiling()`); job video của API, CLI `vlm describe` và `vlm sweep` truyền `get_step_timer(settings.vlm_step_times)`, nên cả hai lượt A (lượt B) và `sweep` theo cùng một biến.
- `segment` — `SegmentTiling`, **mặc định**: các bước phủ kín đoạn. Sắp các bước theo `t_start_rel` (bằng nhau → giữ thứ tự model trả), mốc bắt đầu kẹp vào đoạn và làm tròn 0.01 s, rồi bước đầu bắt đầu ở đầu đoạn, mỗi bước kết thúc lúc bước kế tiếp bắt đầu, bước cuối kết thúc ở cuối đoạn; đoạn có một bước → bước dài bằng cả đoạn. Luật cho trường hợp trùng mốc (để luôn `t_end > t_start`, trừ đoạn dài 0 s): các bước cùng mốc bắt đầu dùng chung một khoảng, từ mốc đó (nhóm đầu: từ đầu đoạn) tới mốc bắt đầu khác kế tiếp hoặc cuối đoạn; bước bắt đầu ở cuối đoạn (sau khi kẹp) dùng chung khoảng của nhóm liền trước. `t_end_rel` của model không được dùng (chỉ còn trong raw answer). AC-24.
- `model` — `ModelSpans`: giữ khoảng model trả, như trước v1.22. Theo thứ tự model trả, `start = min(t_start_rel, d)`, `end = min(max(t_end_rel, t_start_rel), d)` với `d` = độ dài đoạn, cộng `t_start` của đoạn, làm tròn 0.01 s (có thể `t_end = t_start`). AC-28.

Mặc định là `segment` vì đo tốt hơn: video LASI so với bước gán tay `data/video/groundtruth.json`, trên 24 bước lượt A, `model` → `segment`: recall theo thời gian 0.59 → 0.85, precision 0.92 → 1.00, IoU thời gian trung bình 0.34 → 0.50; riêng 17 bước chính: recall 0.81 → 1.00, IoU 0.45 → 0.67; độ dài bước trung vị 1.3 s → 3.1 s (bước gán tay: 2.4 s). Giá trị khác `segment | model` → `Settings` báo lỗi khi nạp cấu hình; tên lạ truyền thẳng vào `get_step_timer` → `ValueError` liệt kê các tên có sẵn. Muốn so hai cách bằng `sweep`: chạy hai lần, mỗi lần một giá trị và một `--out`; chi tiết mỗi cách nằm ở thư mục riêng `sweep-<provider>-<step_times>/` (lần chạy này không ghi đè lần kia), cột `step_times` của CSV và bảng markdown ghi cách đã dùng.

**Lượt B — tự nhất quán.** Chạy lượt A thêm 1 lần (tổng k=2, `temperature=0.2`). Chỉ giữ bước xuất hiện ở cả hai lần (so khớp: `rapidfuzz.token_set_ratio(step) ≥ 70` và overlap thời gian > 0; ghép một-một, điểm cao trước, bằng điểm → theo thứ tự model trả). Bước giữ lại theo thứ tự của lần chạy thứ nhất, nên các bước dùng chung một khoảng (`SegmentTiling`) vẫn giữ thứ tự model trả qua lượt B. `confidence` cuối = trung bình hai lần × tỷ lệ khớp (`token_set_ratio / 100` của cặp). `actor`: hai lần cùng thấy → giữ; một lần không rõ → lấy lần kia; hai lần khác nhau → `null`.

**Song song (`KNOWHOW_VLM_CONCURRENCY`, mặc định 1).** N > 1: hai lần chạy của lượt A (lượt A và lần chạy thêm của lượt B) chạy cùng lúc trên một pool N luồng, tối đa N request VLM cùng lúc; `propose-reasons` trong job video của API cũng chạy N bước một lúc. Kết quả như chạy lần lượt: bước theo thứ tự đoạn, cùng file thô, mỗi đoạn lấy khung hình một lần, mỗi bước một dòng nhật ký lý do (ghi có khoá), tiến độ job chỉ tăng. Lỗi đầu tiên (hay Ctrl+C) dừng như vòng lặp: request chưa gửi của cả hai lần chạy bị huỷ, request đang chạy (tối đa N) chạy nốt, lỗi được báo ra. Làm mờ mặt cho VLM cloud chạy lần lượt (bộ dò mặt không an toàn khi nhiều luồng). N = 1 là đúng luồng cũ; N từ 1 tới 16. Đặt N theo máy chủ: server gộp request (vLLM) sinh nhiều câu trả lời gần bằng giá của một — với model Thinking job ngắn đi nhiều lần; Ollama chỉ trả từng request một. AC-30.

**Lượt C — tổng hợp.** Gọi LLM text (không cần ảnh) với prompt `prompts/pass_c_merge.md`: gộp bước trùng giữa các đoạn kề nhau, sắp `step_order` theo thời gian, chuẩn hóa tên bước (động từ ở đầu). Không được thêm bước mới không có trong input. Mỗi bước đầu vào có mã `s1..sn`; LLM trả `{"steps": [{"step", "source_ids"}]}`. So khớp ngược: bước không có `source_ids` hợp lệ bị bỏ (bịa); bước có tên không khớp nguồn nào (`token_set_ratio < 70`) hoặc gộp đoạn không kề nhau, hoặc gộp hai bước khác `actor` bị từ chối, giữ nguyên các bước nguồn; `actor` của bước gộp lấy từ nguồn (LLM không đổi được); bước đầu vào LLM bỏ sót được giữ nguyên. Nhãn của prompt = nhãn khắt khe nhất của các đoạn (DataGuard chặn LLM cloud với dữ liệu nhà máy).

**Hậu xử lý bắt buộc**
- Ép `reason = None`, `reason_source = None`, `generated_by = "vlm"`, `status = "draft"`.
- Gán `evidence` = video_id, t_start/t_end tuyệt đối, `segment_ids` (mọi đoạn mà bước gộp từ đó), keyframes của đoạn, `transcript_excerpt` từ `align_transcript` (spec 03) nếu có: `describe` đọc `data/work/video/<video_id>/transcript.json` (spec 03 FR-07, list `TranscriptSegment`) và gọi `align_transcript` của spec 03 (FR-08, giả định ở `mentormind.capture.video`, hằng `SPEC03_MODULE`). Thiếu file, file không đọc được, hoặc chưa có hàm của spec 03 → không có excerpt (`None`, chỉ ghi log), `describe` vẫn chạy. Excerpt theo **từng bước**: mỗi câu thuộc đúng một bước — trong các bước lấy từ đoạn mà spec 03 đã gán câu đó, chọn bước có cửa sổ `[t_start − lead, t_end + lag]` trùng câu nhiều nhất (`KNOWHOW_TRANSCRIPT_LEAD_S`, mặc định 2 s: chuyên gia nói trước khi làm; `KNOWHOW_TRANSCRIPT_LAG_S`, mặc định 3 s: nói ngay sau động tác); không bước nào trùng → bước gần câu nhất; bằng nhau → bước trước. Đoạn của câu không có bước nào → câu không vào profile nào. Excerpt của bước = các câu của nó theo thời gian; không câu → `None`. Nhãn của profile = nhãn khắt khe nhất của các đoạn **và** các câu được trích (chỉ câu của chính bước đó). Code ở `processing/vlm/transcript/` (`loader`, `excerpt`); spec 04 không tự gán câu vào đoạn.
- Gán `model_info` = provider, model, fps.
- Validate bằng `validate_against_contract`. JSON lỗi → gọi lại 1 lần với prompt sửa (`prompts/repair_json.md`); vẫn lỗi → ghi segment vào `failed_segments.json`, không crash.
- **Ngôn ngữ:** mọi trường chữ của lượt A (scene, step, hand_action, objects, key_point_observed) phải là tiếng Việt (prompt ghi rõ). Một `step`/`hand_action`/`key_point_observed` từ 2 từ Latin trở lên mà không có chữ cái tiếng Việt nào (`passes/language.py`) → câu trả lời coi như không hợp lệ, dùng chung lượt sửa duy nhất ở trên (lý do: "phải viết bằng tiếng Việt"); lượt sửa vẫn tiếng Anh hoặc hỏng JSON → giữ câu trả lời tiếng Anh, ghi log, không bỏ segment. Đo trên LASI 4/10: model Q4 trên Ollama trả 63–83% tên bước bằng tiếng Anh khi prompt chưa có luật này.

## 4. Prompt lượt A (nội dung chuẩn, lưu tại `processing/vlm/prompts/pass_a_describe.md`)
```
Bạn là kỹ sư IE đang ghi lại thao tác trong công đoạn {process_id} (đóng gói, xếp sản phẩm/linh kiện vào hộp).
Các ảnh sau là khung hình liên tiếp của một đoạn video dài {duration}s, lấy mẫu {fps} khung/giây, theo đúng thứ tự thời gian.
Mốc thời gian (giây, tính từ đầu đoạn) của từng ảnh: {timestamps}.

Bước 1 — "scene": mô tả ngắn (1-2 câu) những gì thấy trong các ảnh: ai hoặc máy/robot nào, đang làm gì.
Bước 2 — "steps": liệt kê CÁC BƯỚC THAO TÁC QUAN SÁT ĐƯỢC của người (công nhân, kỹ sư) hoặc của máy/robot.
Quy tắc:
- Chỉ mô tả điều nhìn thấy trong ảnh. Không suy đoán lý do, không thêm bước "thường có" trong SOP.
- Mỗi bước: động từ ở đầu, ngắn gọn, KHÔNG ghi chủ thể (VD "Đặt linh kiện A vào ngăn trái"); ai làm thì ghi ở "actor".
- actor: ai/cái gì làm bước đó: "human" (người: công nhân, kỹ sư, kỹ thuật viên), "robot" (robot có cánh tay, VD SCARA), "machine" (máy tự động cố định: băng tải, máy dựng thùng, máy chiết rót); không nhìn rõ thì null.
- Một thao tác lặp lại nhiều lần chỉ ghi MỘT bước; tối đa 6 bước cho cả đoạn.
- hand_action: tay nào, động tác gì (nhặt, xoay, ấn, đặt nghiêng...); robot/máy thì tả chuyển động của đầu gắp; objects: vật được thao tác.
- key_point_observed: chi tiết kỹ thuật NHÌN THẤY được (hướng, vị trí, thứ tự), null nếu không có.
- t_start_rel, t_end_rel: giây tính từ đầu đoạn (0 đến {duration}), dựa vào mốc thời gian của ảnh.
- Nếu không chắc, hạ confidence (< 0.5) thay vì bỏ qua hoặc bịa.
- Cảnh chỉ có người nói chuyện, logo, chữ hoặc bảng số liệu thì không phải thao tác: "steps" rỗng.
Trả về DUY NHẤT một đối tượng JSON với hai khóa "scene" và "steps", không markdown, không giải thích.
```
Schema output thêm khóa **`scene`** (bắt buộc, đứng trước `steps`): `{"scene": "str", "steps": [...]}`; mỗi bước có **`actor`** (bắt buộc trong schema, cho phép `null`).
*Vì sao (thí nghiệm 28/9, Qwen3-VL-8B tự host, video demo LASI 20 đoạn × 4 fps):* prompt v1.0 ở trên
trả `{"steps": []}` cho **mọi** đoạn, kể cả có/không `json_schema`; bỏ câu "Không có thao tác nào →
trả {"steps": []}" hoặc dòng JSON mẫu vẫn rỗng; chỉ khi bắt model **mô tả cảnh trước rồi mới trích
bước** thì mới ra bước đúng giờ (robot đặt vào hộp 74.8–79.8 s vs truth 72.6–79.7 s). Thêm dòng mốc
thời gian từng ảnh vì bỏ khung trùng làm khoảng cách giữa các ảnh không còn đều.

## 5. Gắn `reason` từ lời chuyên gia (Should, task S2-6)
`knowhow vlm propose-reasons <video_id>` (và job xử lý video của API spec 08): với mỗi profile **`draft`** có `transcript_excerpt` và chưa có `reason` (`processing/vlm/passes/reasons.py`, hằng số trong code). Bước người duyệt đã xử lý (`in_review`, `approved`, `rejected`) không bị xét lại: không gọi LLM, không ghi nhật ký.

1. **Lời rác không được hỏi**: excerpt có ít hơn `MIN_EXCERPT_LETTERS = 12` chữ cái → không gọi LLM, giữ nguyên profile, quyết định `rejected_junk`. **Chữ cái** = ký tự Unicode loại chữ (`str.isalpha()`, nhóm `L*`): không tính khoảng trắng, chữ số, dấu câu, ký hiệu và dấu kết hợp (dấu nguyên âm/thanh tiếng Thái); một chữ tiếng Việt có dấu là một chữ cái. Đếm chữ cái chứ không đếm từ vì tiếng Thái không có khoảng trắng giữa các từ. VD: "falling" = 7, "3" = 0, "หมด" = 3 → rác; "để tránh cong pin" = 14, "เพื่อเพิ่มประสิทธิภาพ" = 15.
2. **LLM quyết định và chỉ ra đoạn nói mục đích** (`prompts/propose_reason.md`, `temperature=0`, JSON schema): `{"has_reason": bool, "purpose_span": str|null}`. `purpose_span` = đoạn ngắn chép nguyên văn từ lời chuyên gia, chỉ phần nói VÌ SAO / ĐỂ LÀM GÌ của chính bước đó (VD "เพื่อเพิ่มประสิทธิภาพ", "để tránh cong pin"), đúng ngôn ngữ gốc, không dịch, không chép cả câu. Chuyên gia không nói lý do (kể cả chỉ kể việc đang làm, chào hỏi, giới thiệu công ty/dự án, nói về việc khác, chữ rời vô nghĩa) → `{"has_reason": false, "purpose_span": null}`. LLM không được tự suy ra lý do.
3. **Hậu kiểm** — chỉ nhận khi cả hai đúng:
   - *Nguyên văn*: `rapidfuzz.fuzz.partial_ratio(purpose_span, transcript_excerpt) ≥ QUOTE_THRESHOLD = 85`, so trên chuỗi đã lowercase. Đoạn dài hơn cả excerpt → so bằng `fuzz.ratio` với cả excerpt (`partial_ratio` khi đó tìm excerpt bên trong đoạn, nên "cả excerpt + mục đích bịa thêm" được 100). Không khớp → LLM đã diễn giải hoặc bịa: loại (`rejected_not_verbatim`).
   - *Không rác*: `purpose_span` có ít nhất `MIN_SPAN_LETTERS = 6` chữ cái (đếm như trên). Ít hơn → loại (`rejected_junk`).
4. **Điều được lưu là lời chuyên gia**: `reason` = (các) câu đầy đủ của excerpt chứa đoạn khớp, cắt nguyên văn từ excerpt. Đoạn khớp = các ký tự thật sự khớp với `purpose_span` (bỏ ký tự khớp lẻ một mình ở hai mép, khoảng trắng và dấu câu ở hai đầu), không phải cả cửa sổ của `partial_ratio`: cửa sổ dài bằng đoạn nên LLM thêm một chữ là cửa sổ lấn sang câu trước/sau — không phải `purpose_span`, không bao giờ là chữ của AI. Câu tách tại `. ! ? … 。 ！ ？` có khoảng trắng theo sau, hoặc tại xuống dòng; đoạn khớp vắt qua nhiều câu → lấy đủ các câu đó; excerpt không có dấu kết câu (vd. ASR tiếng Thái) là một câu → `reason` = cả excerpt. Nhận → `reason_source = "expert_verbal"`, `status = "in_review"`. Không nhận → giữ nguyên profile (`reason = None`, `status` không đổi). Contract WorkProfile không đổi: `purpose_span` không lưu vào profile.
5. **Nhật ký tự kiểm**: mỗi profile được xét ở trên ghi đúng một dòng JSON (`core.schemas.ReasonAuditRecord`), nối vào `<work_dir>/vlm/<video_id>/reasons_audit.jsonl` — cạnh `describe-<provider>/` của FR-06; CLI: `data/work/vlm/<video_id>/reasons_audit.jsonl`, API: `KNOWHOW_WORK_DIR` (mặc định cũng `data/work`); chạy lại thì nối thêm — và ghi log INFO. Trường: `profile_id, step, transcript_excerpt, has_reason, purpose_span, match_score, junk, junk_why, decision, reason, model, timestamp`. `decision` ∈ `accepted` | `rejected_not_verbatim` | `rejected_junk` | `no_reason` (`has_reason=false` hoặc không có đoạn) | `unreadable` (câu trả lời không phải JSON đúng dạng) | `rejected_contract` (phòng hờ: profile sau khi điền không qua contract). `reason` = điều đã lưu vào profile, không thì `null`; dòng `accepted` chỉ được ghi **sau khi** profile đã lưu (CLI và job API lưu từng profile ngay khi nhận), nên lần chạy dừng giữa chừng (LLM timeout) không để lại dòng `accepted` cho lý do chưa lưu, còn các lý do đã nhận trước đó vẫn được giữ; `has_reason`, `purpose_span`, `match_score`, `model` là `null` khi LLM không được hỏi (excerpt rác).

Mục đích: chặn vi phạm Constitution Điều 3 qua đường gián tiếp. *Vì sao (LASI 08/10, lời tiếng Thái):* với prompt cũ (LLM trả `{"reason"}` rồi chỉ hậu kiểm `partial_ratio ≥ 85`), 7/15 bước có excerpt nhận lý do và lần nào LLM cũng chép cả excerpt, kể cả rác: excerpt chỉ là một từ ASR "falling" được nhận làm lý do; câu kể chuyện công ty ("chúng tôi tìm tự động hóa hiệu năng cao") được nhận cho các bước không liên quan, còn câu bắt đầu bằng "เพื่อ…" ("để…") lại bị loại.

## 6. Quét fps — `knowhow vlm sweep`
```
knowhow vlm sweep --video data/samples/video/pack_demo_01.mp4 \
  --fps 1,2,4,8 --truth data/golden_set/steps/pack_demo_01.json --out data/work/sweep.csv
```
- `truth` là danh sách bước do Đạt gán tay (`[{step, t_start, t_end, key_point?}]`); `key_point` là chi tiết kỹ thuật nhìn thấy được (hướng, góc, vị trí), tùy chọn. File truth có thể là danh sách đó hoặc một object `{"video": ..., "annotation": ..., "scenes": [...], "steps": [...]}`; mỗi bước có thể thêm `essential` (bước thuộc công đoạn chính, mặc định `true`). Mẫu: `data/video/groundtruth.json` (video LASI, 50 cảnh, 27 bước).
- Chưa có `segments.json` của spec 03 thì sweep tự cắt đoạn `fixed_window` 10 s (spec 03 FR-03 fallback, ffmpeg, cache tại `data/work/video/<video_id>/clips/`); có rồi thì truyền `--segments`. Sweep ép cùng một fps cho mọi đoạn (bỏ qua `motion_score`) để so sánh các mức fps.
- So khớp như lượt B. Chỉ số: `recall` (1 − tỷ lệ bỏ sót), `precision` (1 − tỷ lệ bịa), `order_accuracy` (Kendall tau chuẩn hóa), `key_point_recall` (tỷ lệ bước truth có `key_point` được khớp với `key_point_observed` của bước dự đoán tương ứng, `token_set_ratio ≥ 70`; không bước truth nào có `key_point` → để trống), `tokens_used`, `latency_s`.
- Chỉ số phụ (cột thêm, không thay chỉ số chính): `actor_accuracy` (trên bước truth có `actor` và có dự đoán có `actor` trùng thời gian: tỷ lệ dự đoán trùng nhiều nhất có cùng `actor`; truth `worker`/`engineer` tính là `human`), `recall_essential` (chỉ bước `essential`), `recall_time_only` (bước truth có ít nhất một dự đoán trùng thời gian, bất kể câu chữ — đo độ phủ khi luật khớp chữ ≥ 70 quá khắt khe với tiếng Việt tự do), `fps_effective`, `predicted`, `failed_segments`.
- Xuất CSV + in bảng markdown để dán vào slide; CSV và bảng có thêm cột `step_times` (giá trị `KNOWHOW_VLM_STEP_TIMES`, §3); chi tiết mỗi fps (raw answer, `predictions.json`, `profiles_draft.json`) tại `data/work/vlm/<video_id>/sweep-<provider>-<step_times>/fps<N>/`.

## 7. Functional Requirements
- **FR-01** Factory `get_vlm_provider(settings)` theo `KNOWHOW_VLM_PROVIDER` = một tên trong registry:
  `local_openai` (mặc định, server tự host FR-08), `qwen_api` (DashScope), `openrouter`, `siliconflow`,
  `openai_compatible` (server bất kỳ, cần `KNOWHOW_VLM_BASE_URL`), `fake`; `gemini` là Could. Tên lạ →
  `ProviderConfigError` liệt kê các tên có sẵn. `knowhow vlm providers` in registry + trạng thái key.
- **FR-01b** `KNOWHOW_VLM_EXTRA_BODY` (JSON) gộp vào mọi request body cho tham số sampling riêng của vendor
  (vd. `{"presence_penalty": 1.5}`); không bao giờ đè `model`, `messages` hay tham số của chính lời gọi.
- **FR-02** DataGuard chặn trước mọi lời gọi.
- **FR-02b** Frame sampler thích ứng + bỏ khung trùng + trần số ảnh như mục 2.
- **FR-02c** Mọi lời gọi tới provider **cloud** đi qua outbound guard (spec 01 FR-09b, port từ bankassist-mcp): che PII trong prompt/system (`[TYPE_n]`, hoàn nguyên trong câu trả lời), LeakGuard quét lại và **từ chối** nếu còn sót (kể cả khi `KNOWHOW_GUARD_MASK_TEXT=false`), **làm mờ khuôn mặt** trong khung hình (YuNet, model tải một lần, SHA-256 ghim; không tải/không nạp được → từ chối gửi), ghi audit `data/work/audit/outbound-YYYYMMDD.jsonl` (chỉ số đếm, không giá trị). Provider tự host nhận dữ liệu nguyên bản.
- **FR-03** Pipeline 3 lượt như mục 3.
- **FR-04** Hậu xử lý + validate như mục 3.
- **FR-05** CLI: `knowhow vlm describe <video_id> | --segments <file> | --video <file>` (`<video_id>` đọc `data/work/video/<video_id>/segments.json` của spec 03; `--video` cắt bằng `VideoCapturePipeline` của spec 03 (`--method`, mặc định `fixed_window` 10 s như `sweep`; không transcribe — chạy `knowhow video transcribe` trước nếu cần), mỗi đoạn kèm clip và 3 keyframe (spec 03 FR-05/06), ghi `data/work/video/<video_id>/segments.json` nên `describe <video_id>` và API spec 08 đọc lại được; `--no-consistency` bỏ lượt B, `--no-merge` bỏ lượt C; kiểm DataGuard cho cả VLM lẫn LLM **trước** lời gọi đầu tiên), `knowhow vlm propose-reasons <video_id>`, `knowhow vlm sweep ...`; chẩn đoán: `knowhow vlm providers` (registry + key) và `knowhow vlm ping [--provider] [--video --classification]` (clip tổng hợp phụ thuộc thứ tự khung, hoặc video thật; `--classification` mặc định `factory_confidential` để fail-closed).
- **FR-06** Kết quả lưu vào profile store (spec 08) với `status=draft`; lưu raw response mỗi lượt tại `data/work/vlm/<video_id>/` để debug. Nơi lưu chọn bằng `KNOWHOW_PROFILE_SINK` (`processing.vlm.profiles`): `auto` (mặc định) = `ProfileStore` của spec 08 (`knowledge_base.store.profile_store`) nếu có, không thì `data/work/vlm/<video_id>/profiles.json`; `store`/`file` ép một bên. Ghi vào store chỉ thay bản nháp của chính video đó; `profile_id` trùng với profile khác (video khác, hoặc đã duyệt) được dời sang số trống kế tiếp của công đoạn, không bao giờ ghi đè; raw từng lượt ở `data/work/vlm/<video_id>/describe-<provider>/` (`pass_a/`, `pass_b/pass_a/`, `pass_c.json`, `predictions.json`, `failed_segments.json`).
- **FR-07** Retry mạng: tối đa 3 lần, backoff mũ; timeout `KNOWHOW_VLM_TIMEOUT_S` (mặc định 900 s: model Q4 trên Ollama nghĩ khoảng 8k token trước khi trả lời).
- **FR-08** Server tự host tại `3rdparty/vlm_server/` (submodule **mentormind-inference**, https://github.com/osirisQdt2810/mentormind-inference — trước đây vlm-engine; gói Python vẫn là `vlm_server`), mặc định **Ollama + `qwen3-vl:8b` (Q4_K_M)**,
  API OpenAI-compatible ở `127.0.0.1:11434`. `bash 3rdparty/vlm_server/scripts/serve-ollama.sh` (macOS và Linux,
  `make vlm-server`; tùy chọn `--ngrok`) hoặc service `vlm-server` của docker-compose (`docker/Dockerfile.ollama`).
  Cấu hình: `VLM_SERVER_CONTEXT_LENGTH` (mặc định 98304; macOS 49152), `VLM_SERVER_IMAGE_MIN_TOKENS` (mặc định **512**) — số token tối
  thiểu của một ảnh: Ollama tự ép 1024 cho Qwen-VL (frame 448×252 chỉ cần 112), mentormind-inference bọc `llama-server` để chỉnh
  được. Chạy trên **đúng 1 GPU** (`VLM_GPU`/`--gpu`). Backend vLLM (BF16) vẫn còn trong mentormind-inference
  (`VLM_SERVER_BACKEND=vllm`), không còn là mặc định. Code chính chỉ gọi HTTP qua provider `local_openai`, không import
  server.
  Máy chủ suy luận của đội (vd. Vast.ai RTX A5000): `bash run.sh` của repo con (`scripts/vast/run.sh`) dựng vLLM BF16
  (context 64K, KV cache FP8, 512 token/ảnh) + **gateway CPU** (`python -m vlm_server gateway`: ASR, embeddings,
  Docling cho spec 02/03; mọi `/v1/*` khác chuyển tiếp sang vLLM) sau Caddy (token) + ngrok — một URL cho cả
  `KNOWHOW_VLM_BASE_URL` lẫn `KNOWHOW_INFERENCE_URL`; thư viện theo nền tảng ở `requirements/*.txt`.
- **FR-09b** URL theo tài khoản: endpoint có thể khai biến secret cho base URL; `qwen_api` đọc `DASHSCOPE_BASE_URL` (key Singapore mới `sk-ws...` đi kèm host `{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com`), không có thì dùng `dashscope-intl.aliyuncs.com`.
- **FR-09** Secret nằm trong `.env` ở gốc repo (bị `.gitignore` chặn; chỉ `.env.example` được commit;
  `.secrets/README.md` là hướng dẫn lấy key). Cloud provider thiếu key → lỗi nêu đúng tên biến và `.secrets/README.md`.

## 8. Acceptance Criteria
- **AC-01** Với `FakeVLM` + 3 segment fixture → ra WorkProfile hợp lệ contract, `step_order` liên tục từ 1.
- **AC-02** FakeVLM trả JSON có khóa `reason` → profile cuối vẫn `reason=None`.
- **AC-03** Video `factory_confidential` + provider cloud → raise `ConfidentialDataError`, không file nào được đọc.
- **AC-04** Lượt B: bước chỉ xuất hiện ở 1 trong 2 lần chạy bị loại.
- **AC-05** Lượt C không tạo bước không có trong input (test với fake LLM cố tình thêm bước → bị lọc bằng so khớp ngược).
- **AC-06** JSON lỗi 2 lần liên tiếp → segment vào `failed_segments.json`, pipeline vẫn trả kết quả cho các segment khác.
- **AC-07** `sweep` trên fixture ra CSV đủ cột `fps, recall, precision, order_accuracy, key_point_recall, tokens_used, latency_s`.
- **AC-08** `propose-reasons` chỉ điền `reason` khi transcript chứa phát ngôn: FakeLLM trả `{"has_reason": true, "purpose_span": <đoạn có trong excerpt>}` → `reason` điền, `reason_source="expert_verbal"`, `status="in_review"`; `has_reason=false` hoặc `purpose_span=null` → giữ nguyên; profile không có excerpt → không gọi LLM; profile không phải `draft` (`in_review`, `approved`, `rejected`) → không gọi LLM, không có dòng nhật ký.
- **AC-09** FakeLLM trả `purpose_span` là câu diễn giải không có trong `transcript_excerpt` → profile giữ `reason=None`, `status` không đổi (`rejected_not_verbatim`); `purpose_span` = cả excerpt "Bây giờ tôi đặt cốc vào thùng carton" + mục đích bịa thêm "để cốc không bị nứt" → cũng `rejected_not_verbatim`.
- **AC-10** Segment có `motion_score=0.8` → sampler dùng 8 fps; clip fixture gồm các khung giống hệt nhau → sau bỏ trùng còn 1 khung; clip dài cho ra > 48 khung → số ảnh gửi đi = 48.
- **AC-11** Thêm provider mới = 1 class + `@register_vlm("ten")`, dựng được bằng tên qua registry mà không sửa code nghiệp vụ; tên chưa đăng ký → `ProviderConfigError` liệt kê tên có sẵn.
- **AC-12** Provider cloud thiếu key → `ProviderConfigError` nêu tên biến (vd. `OPENROUTER_API_KEY`) và `.secrets/README.md`; key chỉ có trong `.env` vẫn được dùng; `KNOWHOW_VLM_API_KEY` khác rỗng thắng key của vendor, rỗng thì bị bỏ qua.
- **AC-13** `local_openai` trỏ `KNOWHOW_VLM_BASE_URL` tới host public → `is_cloud=True`, dữ liệu `factory_confidential` bị chặn.
- **AC-14** Launcher server (mentormind-inference): backend mặc định `ollama` gọi `scripts/serve-ollama.sh` với `--image-min-tokens`/`--context` từ `VLM_SERVER_*`; backend `vllm`: `VLM_SERVER_GPU="0,1"` bị từ chối, môi trường có `CUDA_VISIBLE_DEVICES` đúng 1 index, lệnh có `--tensor-parallel-size 1`; token không xuất hiện trong argv.
- **AC-15** (thủ công) `make vlm-server` rồi `uv run knowhow vlm ping --frames 48` → `PASS` (model nhận ra hình vuông đỏ đi từ trái sang phải vào hộp); script in `one 448x252 frame = N tokens` với N ≈ `VLM_SERVER_IMAGE_MIN_TOKENS`.
- **AC-16** Provider cloud nhận prompt đã che PII (vd. số điện thoại → `[PHONE_1]`), câu trả lời được hoàn nguyên, audit ghi số lượng đã che; provider tự host nhận prompt nguyên bản; tắt che PII mà prompt còn PII → `SensitiveDataLeakError`, không có HTTP request nào.
- **AC-17** Khung hình gửi provider cloud bị làm mờ vùng mặt (vùng khác giữ nguyên), audit ghi `faces_blurred`; khung gửi provider tự host giữ nguyên byte; không có model làm mờ mặt → từ chối gửi (fail closed).
- **AC-18** Lượt A: mỗi bước có `actor` ∈ {`human`, `robot`, `machine`, `null`}; từ đồng nghĩa ("công nhân", "kỹ sư", "robot SCARA", "máy dựng thùng") được chuẩn hóa, từ không nhận ra → `null`, segment không bị loại; WorkProfile mang `actor`, hợp lệ contract; `actor` ngoài enum bị cả Pydantic lẫn contract từ chối.
- **AC-19** Lượt B: hai lần chạy khác `actor` → `actor=null`. Lượt C: không gộp hai bước khác `actor`; bước gộp giữ `actor` của nguồn dù LLM trả gì.
- **AC-20** Lượt A trả tên bước tiếng Anh (vd. "Pick product") → hỏi lại 1 lần với prompt sửa nêu yêu cầu tiếng Việt và trường sai; lần 2 tiếng Việt → giữ bản tiếng Việt; lần 2 hỏng → giữ bản tiếng Anh, segment không bị đánh dấu lỗi.
- **AC-21** Fallback `fixed_window` (ffmpeg giả lập, video tổng hợp): mỗi đoạn có đúng 3 keyframe JPG tồn tại trên đĩa, cạnh dài ≤ 768 px, chạy lại không ghi lại ảnh đã có; `segments.json` đọc lại được thành đúng các `Segment` đó; WorkProfile của bước mang keyframe của đoạn.
- **AC-23** `KNOWHOW_LOCAL_HOSTS=["vlm-team.ngrok-free.dev"]`: `local_openai` trỏ `https://user:pass@VLM-team.ngrok-free.dev/v1` → `is_cloud=False`, nhận dữ liệu `factory_confidential`, khung hình không bị làm mờ; host public khác (kể cả `x.vlm-team.ngrok-free.dev`) vẫn cloud; `openrouter` vẫn cloud dù host của nó có trong danh sách; danh sách rỗng (mặc định) → hành vi như AC-13.
- **AC-22** Transcript theo bước: hai bước cùng một đoạn nhận hai câu khác nhau (mỗi câu về bước trùng thời gian); câu nói ngay sau động tác (trong `lag`) về đúng bước vừa làm; câu vắt ranh giới hai bước về bước trùng nhiều hơn; bước không câu nào có `transcript_excerpt=None`; `propose-reasons` vẫn chỉ nhận `reason` khớp excerpt của chính bước đó.
- **AC-24** Lượt A: các bước của một đoạn phủ kín đoạn theo thứ tự bắt đầu — bước đầu từ đầu đoạn, mỗi bước kết thúc ở lúc bước sau bắt đầu, bước cuối tới cuối đoạn; đoạn có một bước → bước dài bằng cả đoạn; hai bước cùng mốc bắt đầu dùng chung một khoảng, mọi bước có `t_end > t_start`; sau lượt B các bước chung khoảng vẫn theo thứ tự model trả (kể cả khi bước sau khớp điểm cao hơn).
- **AC-25** Lời rác (§5): excerpt "falling" (7 chữ cái < 12), "3", "หมด" → không gọi LLM, `reason=None`, `status` không đổi, quyết định `rejected_junk`; `purpose_span` dưới 6 chữ cái (vd. "vì nếu") dù có nguyên văn trong excerpt → `rejected_junk`; đếm chữ cái theo Unicode: "để tránh cong pin" = 14, "เพื่อเพิ่มประสิทธิภาพ" = 15 (dấu kết hợp tiếng Thái không tính), "3 , . !" = 0.
- **AC-26** Điều được lưu là câu của chuyên gia: excerpt "Nhặt cốc lên nhé. Đặt cốc vào thùng, xếp nghiêng để cốc không bị nứt! Xong rồi." + `purpose_span` "Để cốc không bị nứt" → `reason` = "Đặt cốc vào thùng, xếp nghiêng để cốc không bị nứt!" (cả câu chứa đoạn, không phải đoạn); đoạn vắt qua hai câu → `reason` = đủ hai câu, nguyên văn; excerpt không dấu kết câu (ASR tiếng Thái) → `reason` = cả excerpt; `purpose_span` thừa một chữ ở đầu ("vì để cốc không bị nứt") hoặc ở cuối ("để cốc không bị nứt vỡ") → vẫn chỉ câu chứa đoạn, không lấn sang câu trước/sau.
- **AC-27** Nhật ký tự kiểm: mỗi profile được xét ghi đúng một dòng vào `<work_dir>/vlm/<video_id>/reasons_audit.jsonl` (đủ 12 trường của §5, UTF-8 đọc được) với `decision` đúng cho từng trường hợp `accepted` / `rejected_not_verbatim` / `no_reason` / `unreadable` / `rejected_junk`, kèm một log INFO; profile không có excerpt không có dòng; chạy lại thì nối thêm; `knowhow vlm propose-reasons` và job video của API ghi cùng chỗ; LLM lỗi ở profile thứ hai → profile thứ nhất đã được lưu cùng dòng `accepted` của nó; lưu lỗi → không có dòng `accepted`.
- **AC-28** `KNOWHOW_VLM_STEP_TIMES` qua `Settings` → `get_step_timer` → lượt A, cùng một câu trả lời của FakeVLM: không đặt hoặc `segment` → các bước phủ kín đoạn như AC-24; `model` → khoảng của model kẹp vào đoạn như trước v1.22 (thứ tự model trả, mốc quá cuối đoạn → cuối đoạn, `t_end_rel < t_start_rel` → `t_end = t_start`), ở cả hai lượt A của `DescribePipeline`, trong job video của API, qua CLI `vlm describe` (WorkProfile lưu ra) và `vlm sweep` (`predictions.json` trong `sweep-<provider>-<step_times>/`, cột `step_times`); giá trị khác (vd. `auto`) → `Settings` báo lỗi; `get_step_timer("auto")` → `ValueError` liệt kê `segment, model`; mỗi giá trị của `Settings` là một tên trong `STEP_TIMERS`.
- **AC-29** Câu trả lời không có chữ (`message.content = null`, vd. model Thinking qua vLLM `--reasoning-parser` dùng hết `max_tokens` khi còn đang suy luận) là câu trả lời rỗng, không phải lỗi provider: `generate` trả `text=""`, `generate_json` → `InvalidJSONError` (lượt A hỏi lại/đánh dấu đoạn lỗi, lượt C bỏ gộp như với JSON hỏng); `propose-reasons` ghi `unreadable`, giữ bản nháp và xét tiếp bước sau — job video không còn báo lỗi cả job vì một câu trả lời rỗng.
- **AC-30** `KNOWHOW_VLM_CONCURRENCY` (mặc định 1, phải ≥ 1): `DescribePipeline(concurrency=3)` với VLM giả trả lời theo đoạn → WorkProfile, bước và file thô y hệt `concurrency=1`; số request đồng thời đạt đúng 3 và không vượt 3 (1 khi `concurrency=1`); đoạn đầu trả lời sau cùng vẫn đứng đầu; mỗi đoạn lấy khung hình đúng một lần dù hai lần chạy chồng nhau; job video của API (N = 1 và N = 3): cùng danh sách bước nháp và lý do, tiến độ `describe`/`reasons` chỉ tăng tới đủ, mỗi bước xét lý do đúng một dòng nhật ký; VLM cloud với N = 4: các request vẫn chồng nhau nhưng không lần dò mặt nào chạy cùng lúc; một đoạn lỗi mãi (503) → `ProviderError`, chỉ thêm tối đa 2N request sau lỗi (không treo).

## 9. Tasks
- [x] T04-1 Provider protocol + `OpenAICompatVLM` + `FakeVLM` + factory + DataGuard (AC-03).
- [x] T04-2 Frame sampler từ clip (fps thích ứng, bỏ trùng, trần số ảnh, resize) (AC-10).
- [x] T04-3 Lượt A + prompt + validate + repair (AC-01, AC-02, AC-06). *(Nối vào profile store chờ spec 08; hiện ghi `profiles_draft.json`.)*
- [x] T04-4 Lượt B tự nhất quán (AC-04).
- [x] T04-5 Lượt C tổng hợp (AC-05).
- [x] T04-6 `sweep` + `key_point_recall` (AC-07).
- [x] T04-7 `propose-reasons` + hậu kiểm trích dẫn (AC-08, AC-09). *(`describe` điền `transcript_excerpt` khi có `transcript.json` của spec 03; chưa có thì lệnh không làm gì.)*
- [x] T04-8 Registry provider dùng chung (`core.providers`) + cloud `openrouter`/`siliconflow` + key từ `.env` + `knowhow vlm providers|ping` (AC-11, AC-12, AC-13).
- [x] T04-9 Server tự host `3rdparty/vlm_server` (vLLM, Qwen3-VL-8B-Instruct, 1 GPU) + smoke test (AC-14, AC-15).
- [x] T04-10 Outbound guard cho VLM cloud: che PII + LeakGuard + làm mờ mặt + audit (AC-16, AC-17).
- [x] T04-11 Trường `actor` (human/robot/machine) qua lượt A → B → C → WorkProfile + `actor_accuracy` trong sweep (AC-18, AC-19).
- [x] T04-12 Chuyển server tự host sang Ollama (`qwen3-vl:8b` Q4, `image-min-tokens` chỉnh được, script macOS/Linux + ngrok) (FR-08, AC-14, AC-15).
- [x] T04-13 Lượt A trả lời bằng tiếng Việt: luật trong prompt + hậu kiểm ngôn ngữ dùng chung lượt sửa (AC-20).
- [x] T04-14 Fallback `--video`: 3 keyframe mỗi đoạn + ghi `segments.json` của video (dùng chung cho CLI và API spec 08, `processing/vlm/segments.py`) (AC-21).
- [x] T04-15 Transcript theo từng bước (`lead`/`lag`), `--video` qua `VideoCapturePipeline` của spec 03 (AC-22).
- [x] T04-16 `KNOWHOW_LOCAL_HOSTS`: host tự khai báo là local (vd. ngrok tới Mac tự host của đội) (AC-23).
- [x] T04-17 Lượt A: các bước của một đoạn phủ kín đoạn theo thứ tự bắt đầu, thay cho khoảng ~1 s model trả (AC-24).
- [x] T04-18 `propose-reasons` trích đoạn nói mục đích: LLM trả `has_reason` + `purpose_span`, hậu kiểm nguyên văn + lọc rác theo số chữ cái, `reason` = câu đầy đủ của chuyên gia, nhật ký `reasons_audit.jsonl` (AC-08, AC-09, AC-25, AC-26, AC-27).
- [x] T04-19 `KNOWHOW_VLM_STEP_TIMES` (`segment` mặc định | `model`): hai lớp `SegmentTiling`/`ModelSpans` của `StepTimer` + registry `get_step_timer` (`passes/step_times.py`), tiêm vào `describe_segments`/`DescribePipeline` từ API, CLI `describe` và `sweep`; `sweep` tách thư mục chi tiết theo cách và thêm cột `step_times` (AC-28).
- [x] T04-20 Sửa sau review: lượt B giữ thứ tự model cho bước chung khoảng; `propose-reasons` chỉ xét bản nháp, đoạn dài hơn excerpt so bằng `ratio`, câu chứa đoạn theo ký tự thật sự khớp, dòng `accepted` chỉ ghi sau khi lưu (AC-08, AC-09, AC-24, AC-26, AC-27).
- [x] T04-21 `message_text`: `content = null` → chuỗi rỗng (`core/providers/openai_compat/chat.py`) (AC-29).
- [x] T04-22 `KNOWHOW_VLM_CONCURRENCY`: `describe_segments(executor=...)`, `DescribePipeline(concurrency=...)` chạy hai lần lượt A trên một pool, cache khung hình có khoá; job video và CLI `vlm describe` đọc cài đặt; `propose-reasons` song song trong job (lưu và nhật ký có khoá); `passes/parallel.wait_first_error` dừng ở lỗi đầu tiên; khoá làm mờ mặt theo provider (AC-30).

## Changelog
- v1.0 (23/9): khởi tạo.
- v1.1 (23/9): hậu xử lý gán `evidence.segment_ids` (contract WorkProfile thêm field).
- v1.2 (24/9): FR-02b lấy mẫu thích ứng theo `motion_score` + bỏ khung trùng + `KNOWHOW_VLM_MAX_FRAMES`; `sweep` thêm `key_point_recall`; hậu kiểm `reason` phải khớp transcript (AC-09, AC-10).
- v1.3 (27/9): đường dẫn module theo layout mới (bỏ `knowhow.`/`src/knowhow/`, xem spec 01 v1.3).
- v1.4 (28/9, Phúc): provider theo registry (`core.providers` + `@register_vlm`), thêm `openrouter`, `siliconflow`, `openai_compatible`; `generate` là template method chạy DataGuard trước khi đọc file; FR-01b `KNOWHOW_VLM_EXTRA_BODY`; FR-08 server tự host `3rdparty/vlm_server` trên 1 GPU; FR-09 secret trong `.secrets/`; AC-11..AC-15; T04-1, T04-2, T04-8, T04-9 xong. Đo trên A5000: 48 khung ≈ 5.5k token, 2.9–3.8 s. Lưu ý: Alibaba ngừng `qwen3-vl-8b-instruct` ngày 10/10/2026.
- v1.5 (28/9, Phúc): prompt lượt A thêm bước mô tả `scene` trước `steps` + mốc thời gian từng ảnh (§4, kèm số liệu thí nghiệm); FR-02c outbound guard cho cloud (che PII, LeakGuard, làm mờ mặt, audit) + AC-16, AC-17, T04-10; sweep nhận truth dạng object, fallback `fixed_window` khi chưa có spec 03, thêm cột phụ `recall_essential`/`recall_time_only`; T04-3, T04-6 xong; package `processing/vlm/` chia theo chức năng.
- v1.6 (28/9, Phúc): FR-09b `DASHSCOPE_BASE_URL` cho host workspace Singapore (tài liệu Alibaba 28/9).
- v1.7 (28/9, Phúc): FR-09 + AC-12 key đọc từ `.env` (không còn `.secrets/secrets.env`); `.secrets/README.md` chỉ là hướng dẫn lấy key.
- v1.8 (28/9, Phúc): lượt A nhận `objects` dạng chuỗi "a, b" (DashScope `json_object` không ép schema, gặp khi chạy cloud trên video LASI); AC-15 chạy thật trên MI250 (GCD 1, vLLM 0.23 ROCm): PASS.
- v1.9 (28/9, Phúc): T04-4 lượt B, T04-5 lượt C (`pass_c_merge.md`, so khớp ngược), T04-7 `propose-reasons` (`propose_reason.md`, `partial_ratio ≥ 85`) xong; `processing.vlm.pipeline.describe_video` nối A → B → C → hậu xử lý; FR-05 `describe` nhận thêm `--video`/`--segments`; FR-06 lưu tạm `profiles.json` khi chưa có spec 08.
- v1.10 (28/9, Phúc): pipeline là class `DescribePipeline` (`pass_a`/`pass_b`/`pass_c`/`postprocess`/`run`) thay cho hàm `describe_video`.
- v1.11 (28/9, Phúc): T04-11 `actor` = ai làm bước (`human` gộp công nhân + kỹ sư, `robot`, `machine`, `null`); prompt lượt A v1.6: tên bước không ghi chủ thể, `hand_action` chỉ còn động tác; lượt B/C giữ và kiểm `actor`; sweep thêm `actor_accuracy`; contract WorkProfile thêm `actor` (AC-18, AC-19).
- v1.12 (28/9, Phúc): provider VLM chuyển `processing.vlm.providers` → `core.providers.vlm`, làm mờ mặt `processing.vlm.guard.face_blur` → `core.guard.image` (§2).
- v1.13 (28/9, Phúc): guard ảnh thành package `core.guard.image` (`face_blur` là cách đầu tiên; chỗ để thêm cách khác).
- v1.14 (29/9, Phúc): FR-06 lưu vào profile store của spec 08 khi có (`KNOWHOW_PROFILE_SINK=auto|store|file`), không ghi đè profile của video khác.
- v1.15 (29/9, review): FR-06 sửa lỗi mất dữ liệu — profile vừa đổi `profile_id` trong cùng một lần lưu không còn bị profile sau của cùng video ghi đè.
- v1.16 (4/10, Phúc): hậu xử lý điền `transcript_excerpt` từ `transcript.json` của spec 03 (§3), viết trước theo đúng output spec 03 (`transcript.json` + `align_transcript` gọi qua import, thiếu thì `None`) để `propose-reasons` chạy được ngay khi spec 03 xong.
- v1.17 (4/10, Phúc): FR-08 server tự host chuyển sang Ollama + `qwen3-vl:8b` Q4 (demo chạy trên Ollama); `VLM_SERVER_IMAGE_MIN_TOKENS` thay mức 1024 Ollama tự ép; FR-07 timeout mặc định 900 s, `KNOWHOW_VLM_MAX_TOKENS` 16384 cho phần thinking; T04-12.
- v1.18 (4/10, Phúc): §3 lượt A phải trả tiếng Việt (prompt + hậu kiểm `passes/language.py`, dùng chung lượt sửa), AC-20, T04-13; đo LASI: model Q4 trả 63–83% tên bước bằng tiếng Anh.
- v1.19 (06/10, Phúc): FR-05 fallback `--video` sinh 3 keyframe/đoạn (spec 03 FR-05, cache) và ghi `data/work/video/<video_id>/segments.json` để `describe <video_id>`, API spec 08 (job xử lý video, `GET /videos/{id}/segments`) và trang duyệt dùng lại; `probe_video` tạm thay `video probe` của spec 03; AC-21, T04-14. Khi spec 03 xong chỉ bước cắt đổi, phần đọc `segments.json`/`transcript.json` giữ nguyên.
- v1.20 (06/10, Phúc): §3 transcript theo **từng bước** thay vì theo đoạn: mỗi câu (đã được spec 03 gán vào đoạn) thuộc đúng một bước — cửa sổ `[t_start − lead, t_end + lag]` trùng nhiều nhất (`KNOWHOW_TRANSCRIPT_LEAD_S`=2, `KNOWHOW_TRANSCRIPT_LAG_S`=3), rồi phần trùng với chính bước, rồi bước trước; không trùng → bước gần nhất. Trước đây mọi bước của một đoạn trích chung mọi câu của đoạn, nên `propose-reasons` có thể gán lý do của bước này cho bước kia. `--video` cắt bằng `VideoCapturePipeline` của spec 03 (`--method`). AC-22, T04-15.
- v1.21 (07/10, Phúc): FR-01 `is_cloud`: `KNOWHOW_LOCAL_HOSTS` cho phép khai báo đích danh hostname là local (đồng nghiệp gọi Ollama trên Mac của đội qua ngrok); chỉ `local_openai`/`openai_compatible`, khớp đúng cả tên, vendor cloud không đổi. AC-23, T04-16.
- v1.22 (08/10, Phúc): §3 hậu xử lý lượt A: các bước của một đoạn phủ kín đoạn theo thứ tự bắt đầu (bước k từ lúc nó bắt đầu tới lúc bước k+1 bắt đầu, bước đầu từ đầu đoạn, bước cuối tới cuối đoạn; cùng mốc → chung khoảng), bỏ `t_end_rel` của model. Đo LASI: trung vị 1.4 s/bước, 22/32 bước ≤ 2 s nên trang duyệt chỉ phát ~1 s và lượt B bỏ bước cùng tên lệch giây. AC-24, T04-17.
- v1.23 (08/10, Phúc): §5 `propose-reasons`: LLM trả `{"has_reason", "purpose_span"}` (đoạn ngắn nguyên văn nói vì sao/để làm gì) thay cho `{"reason"}`; nhận khi đoạn khớp excerpt (`partial_ratio ≥ 85`) và không rác (đoạn ≥ 6 chữ cái Unicode, excerpt ≥ 12, excerpt rác thì không hỏi LLM); `reason` lưu là câu đầy đủ của chuyên gia chứa đoạn, không phải đoạn; mỗi profile một dòng `reasons_audit.jsonl` để tự kiểm. Đo LASI (tiếng Thái): prompt cũ cho 7/15 bước lý do, đều chép cả excerpt, kể cả từ rác "falling". AC-08, AC-09 cập nhật; AC-25..AC-27, T04-18.
- v1.24 (08/10, Phúc): §3 thời gian của bước thành hai cách chọn bằng `KNOWHOW_VLM_STEP_TIMES`: `segment` (mặc định, các bước phủ kín đoạn như v1.22) và `model` (khoảng model trả, kẹp vào đoạn như trước v1.22); hai lớp `SegmentTiling`/`ModelSpans` của `StepTimer`, registry `STEP_TIMERS` + `get_step_timer` (`processing/vlm/passes/step_times.py`), tiêm vào `describe_segments`/`DescribePipeline` từ API, CLI `describe` và `sweep` (`sweep` ghi chi tiết vào `sweep-<provider>-<step_times>/` và thêm cột `step_times` để hai lần chạy không ghi đè nhau). Mặc định `segment` vì đo LASI so với `data/video/groundtruth.json` (24 bước lượt A): recall thời gian 0.59 → 0.85, precision 0.92 → 1.00, IoU thời gian 0.34 → 0.50; 17 bước chính: recall 0.81 → 1.00, IoU 0.45 → 0.67; độ dài trung vị 1.3 s → 3.1 s (gán tay 2.4 s). AC-28, T04-19.
- v1.25 (08/10, Phúc, review): §3 lượt B trả bước theo thứ tự lần chạy thứ nhất — với `SegmentTiling` các bước chung khoảng bị đảo theo điểm khớp (bước 1 thành bước 2, transcript về nhầm bước). §5: chỉ xét profile `draft` (trước đây bước đã từ chối/duyệt bị xét lại rồi lưu thành profile `in_review` trùng); đoạn dài hơn excerpt so bằng `fuzz.ratio` (trước đây "cả excerpt + mục đích bịa" được 100 và nhận); câu được lưu theo ký tự thật sự khớp (LLM thêm một chữ không còn kéo theo câu bên cạnh); dòng `accepted` của nhật ký chỉ ghi sau khi profile đã lưu, CLI và job API lưu từng profile ngay khi nhận. §3 dẫn đúng AC-28 cho `model`. AC-08, AC-09, AC-24, AC-26, AC-27 bổ sung; T04-20.
- v1.26 (08/10, Phúc): FR-08 submodule đổi tên vlm-engine → mentormind-inference (`033ad10`): thêm gateway CPU (ASR, embeddings, Docling, proxy VLM), `run.sh` dựng máy chủ suy luận của đội (vLLM 64K FP8 + gateway + Caddy + ngrok), requirements theo nền tảng; đã chạy thật trên Vast RTX A5000.
- v1.27 (08/10, Phúc): câu trả lời `content = null` là câu trả lời rỗng (AC-29, T04-21). Đo trên LASI: 8B Thinking FP8 suy luận hết 16 384 token ở một bước `propose-reasons`, vLLM trả `content = null`, provider báo `Unexpected message content type: NoneType` và cả job video (đã lưu 24 bước nháp) thành lỗi.
- v1.28 (08/10, Phúc): FR-08 submodule mentormind-inference → `8dc3768`: `run.sh` mặc định 8B Thinking FP8 + ngram (cấu hình đã chọn), chọn model khác (`VLM_VARIANT` instruct | thinking | thinking-fp8 | 30b-thinking, `VLM_MODEL`), `SPEC_CONFIG` (speculative decoding), `JSON_WHITESPACE=compact`; gateway heartbeat (`INFERENCE_HEARTBEAT_S`: câu trả lời chậm qua ngrok không còn bị cắt 503 sau ~5 phút); báo cáo so sánh model trên LASI `benchmarks/lasi-vlm/README.md`.
- v1.29 (08/10, Phúc): `KNOWHOW_VLM_CONCURRENCY` (§3, AC-30, T04-22). Đo trên LASI: job 8B Thinking FP8 gửi lần lượt từng request nên GPU chỉ sinh cho một câu trả lời (59 token/giây) dù KV cache chứa được ~6 request; chạy trọn job mất khoảng 73 phút (cắt đoạn và lời nói 2.4 + lượt A 26 + lượt B 25 + gộp 4 + lý do ~15). Mặc định 1 giữ đúng luồng cũ. Đo lại trên UI: FP8 + ngram + `KNOWHOW_VLM_CONCURRENCY=4` → cả job 22.9 phút (lượt A và B 18 phút thay vì 51), danh sách cuối không kém (chấm mù, `mentormind-inference/benchmarks/lasi-vlm/README.md`).
