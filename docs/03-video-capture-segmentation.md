# 03 — Video Capture, Segmentation & Transcript

**Owner:** Việt Hoàng · **Tasks Excel:** S0-7 (dữ liệu, Đạt), S1-2, S2-6

## 1. Mục tiêu
Cắt video thao tác thành các đoạn ngắn có ranh giới hợp lý để VLM (spec 04) mô tả chính xác, trích keyframe làm minh họa SOP, và chuyển lời bình luận của chuyên gia thành transcript có timestamp.

## 2. Vì sao phải tự cắt đoạn trước khi đưa VLM
VLM lấy mẫu thưa (mặc định ~1 fps) sẽ bỏ sót động tác tay nhanh. Cắt trước thành đoạn 5–15s cho phép đẩy fps cao trên từng đoạn mà không tốn token.

## 3. Data model — `core.schemas.video`
```python
class VideoAsset(BaseModel):
    video_id: str  # "VID-" + sha256[:12]
    path: str
    duration_s: float
    fps: float
    has_audio: bool
    process_id: str | None
    data_classification: DataClassification


class Segment(BaseModel):
    segment_id: str  # f"{video_id}-S{index:03d}"
    video_id: str
    index: int
    t_start: float
    t_end: float
    method: Literal["scene", "hand_activity", "fixed_window"]
    motion_score: float | None  # 0..1, None nếu không tính
    keyframes: list[str]  # đường dẫn JPG
    clip_path: str  # mp4 đã cắt
    data_classification: (
        DataClassification  # kế thừa từ VideoAsset, để DataGuard (spec 04) kiểm tra không cần tra ngược
    )


class TranscriptSegment(BaseModel):
    video_id: str
    t_start: float
    t_end: float
    text: str
    language: str
    source: Literal["inline", "cued_recall"] = "inline"  # lời bình khi quay / ghi âm video-cued recall
    data_classification: DataClassification
```

## 4. Kiến trúc — chỉ CPU, tập trung thao tác của người
Hệ thống mô tả thao tác của **người**; không có xử lý riêng cho robot/máy (VLM vẫn ghi `actor`, spec 04 §3). Mọi bước chạy trên CPU.

```
mentormind/capture/video/          (import nhẹ: thư viện nặng chỉ nạp trong hàm dùng nó)
  probe.py        video_id_for, probe (FR-01)
  segmenters/     base (Segmenter, Cut, chuỗi fallback), fixed_window, scene, hand_activity, motion
  postprocess.py  FR-04
  media.py        keyframe (FR-05), clip (FR-06)
  transcribe.py   FR-07/07b: câu từ word timestamps, recall audio
  align.py        align_transcript (FR-08) — export ở mentormind.capture.video (spec 04 import theo tên)
  store.py        đọc/ghi video.json, segments.json, transcript.json
  pipeline.py     VideoCapturePipeline (FR-09)
  cli.py          knowhow video probe|segment|transcribe|providers
mentormind/core/providers/asr/     ASR là provider như VLM/LLM (FR-07c): faster_whisper tại máy, remote trên máy chủ suy luận
```
Fallback `fixed_window` + keyframe mà spec 04 viết tạm (`processing/vlm/segments.py`, `sweep/windows.py`) chuyển hết vào đây; `processing/vlm` chỉ import lại, không giữ bản thứ hai.

## 5. Functional Requirements
- **FR-01** `knowhow video probe <file> [--process-id] [--classification]` trả `VideoAsset` (ffprobe: thời lượng, fps, có audio không; `video_id` = `VID-` + sha256[:12] nội dung). Máy không có ffprobe: OpenCV đọc thời lượng/fps, video coi như không có audio (ghi log).
- **FR-02** `knowhow video segment <file> --process-id PACK01 --classification synthetic [--method]` tạo `Segment` list + file JSON tại `data/work/video/<video_id>/segments.json`, kèm `video.json` (`VideoAsset`), keyframe và clip.
- **FR-03** Chiến lược cắt, chọn bằng `--method`; không truyền thì theo `KNOWHOW_VIDEO_METHOD` (mặc định `hand_activity`; video đã dựng nhiều cảnh như LASI nên dùng `scene`); thiếu thư viện/model của một cách, cách đó lỗi khi chạy, hoặc không áp dụng được (vd. hầu như không thấy tay) thì rơi xuống cách sau, ghi log cảnh báo kèm lý do, không crash, và báo cách thực dùng; chỉ `fixed_window` (cuối chuỗi) lỗi mới báo lỗi:
  1. `hand_activity` (Should): MediaPipe Tasks `HandLandmarker` (CPU; model `hand_landmarker.task` tải một lần vào `KNOWHOW_VIDEO_HAND_MODEL`, ghim SHA-256). Khung thu nhỏ cạnh dài 256 px, 5 fps. Năng lượng = tốc độ cổ tay (landmark 0) trung bình các bàn tay thấy được, đơn vị bề rộng khung/giây; không thấy tay = nghỉ. Ranh giới ở giữa mỗi quãng năng lượng < 0.05 kéo dài ≥ 0.4 s. Thấy tay ở < 10% số khung (cảnh robot, cảnh phỏng vấn — LASI: 3,3%) → không áp dụng, rơi xuống `scene`.
  2. `scene` (Must): PySceneDetect `ContentDetector` (ngưỡng 27, khung thu nhỏ). Import `scenedetect` không nạp PyAV (đọc bằng OpenCV; trên macOS PyAV và OpenCV cùng đóng gói libavdevice → cảnh báo trùng class Objective-C, có thể crash).
  3. `fixed_window` (Must, fallback): cửa sổ 10 s.

  Mỗi đoạn có `motion_score` 0..1 cho sampler của spec 04: `hand_activity` = tốc độ cổ tay trung bình / 0.5 (cắt ở 1); `scene`, `fixed_window` = chênh lệch điểm ảnh trung bình giữa hai khung liên tiếp (xám, 160 px, 4 fps) / 20 (cắt ở 1).
- **FR-04** Hậu xử lý: gộp đoạn < 3 s vào đoạn liền trước (đoạn đầu: liền sau); tách đoạn > 20 s thành các phần bằng nhau ≤ 15 s. Video ngắn hơn 3 s là một đoạn.
- **FR-05** Mỗi đoạn xuất 3 keyframe (đầu, giữa, cuối − 0.05 s) JPG, cạnh dài ≤ 768 px, ở `data/work/video/<video_id>/keyframes/<segment_id>_k{0,1,2}.jpg`; đã có thì không ghi lại.
- **FR-06** Mỗi đoạn xuất `clip_path` mp4 ở `data/work/video/<video_id>/clips/<segment_id>.mp4`: luôn re-encode H.264 (`yuv420p`, `+faststart`, rộng 640 px; video có audio thì giữ tiếng, AAC — người duyệt cần nghe chuyên gia nói trong đoạn; video câm thì không có track audio) — `-c copy` cắt ở keyframe của nguồn nên lệch ranh giới, và codec nguồn có thể không phát được trên trình duyệt (UI spec 08 phát clip). Clip xuất theo định dạng cũ (đánh dấu `clips/.format` khác) được xuất lại, kể cả khi ranh giới đoạn không đổi.
- **FR-07** `knowhow video transcribe <file> [--classification]` (Should; ngôn ngữ theo FR-07c, mặc định tự nhận — FR-07 v1.0 ghi `vi`): nếu `has_audio`, tách audio (ffmpeg → WAV 16 kHz mono, không nạp cả video vào RAM) rồi gọi ASR provider (FR-07c) → câu cắt theo word timestamps (dấu `. ? ! …`, quãng lặng ≥ 0.8 s, hết một đoạn nói Whisper trả về, hoặc câu dài quá 15 s thì cắt ở ranh giới từ kế tiếp — không bao giờ cắt giữa một từ, kể cả ngôn ngữ viết liền như tiếng Thái) → `TranscriptSegment` list tại `transcript.json` (thay các câu `inline` cũ, giữ câu `cued_recall`). Không dùng ASR của bên thứ ba (`remote` là máy chủ của đội, FR-07c).
- **FR-07b** `knowhow video transcribe --recall-audio <audio_file> --video-id <VID-...> [--offset <s>]` (Should): nhận file ghi âm video-cued recall (architecture mục 4) cho video câm. Timestamp transcript = timestamp audio + `offset` (mặc định 0, tức chuyên gia bắt đầu ghi âm cùng lúc phát video). Kết quả `source="cued_recall"`, `data_classification` lấy từ `VideoAsset` (`video.json`), ghi vào `transcript.json` của video đó. Một bản ghi âm sở hữu khoảng video nó phủ (`offset` → `offset` + độ dài audio): câu `cued_recall` cũ bắt đầu trong khoảng đó bị thay, câu ngoài khoảng và câu `inline` giữ nguyên — chạy lại cùng bản ghi không nhân đôi câu (ASR chia câu khác nhau mỗi lần nên không so được theo chữ).
- **FR-07c** ASR là provider như VLM/LLM (spec 04 §2, constitution Điều 5): `core.providers.asr` — `ASRProvider(ProviderBase)` với template method `transcribe(audio, *, classification, language)` chạy `DataGuard` **trước** khi đọc file rồi gọi `_transcribe`; registry `@register_asr`, `get_asr_provider(settings)`, `catalog`, lỗi qua `core.providers.errors`. Backend: `faster_whisper` (local, `is_cloud=False`, CPU `int8`, model `small`, `word_timestamps`, VAD), `remote` và `fake` (kịch bản, cho test); không có backend API bên thứ ba. `remote` = Whisper trên máy chủ suy luận riêng của đội (`KNOWHOW_INFERENCE_URL`, cùng máy chủ với Docling/bge-m3 của spec 02 FR-02c/FR-07d): `POST {url}/audio/transcriptions` multipart `file` (WAV), `response_format=verbose_json`, `timestamp_granularities[]=word`, `language` chỉ khi ép ngôn ngữ, `model` chỉ khi đặt `KNOWHOW_ASR_MODEL` (trống = model mặc định của máy chủ); Bearer `KNOWHOW_INFERENCE_API_KEY` (trống → `KNOWHOW_VLM_API_KEY` khi `KNOWHOW_VLM_BASE_URL` cùng host, spec 02 §2), basic auth trong URL được; timeout `KNOWHOW_INFERENCE_TIMEOUT_S` (1800 s; kết nối 10 s); file đã gửi mà hết giờ chờ trả lời thì không gửi lại (spec 02 §2). Câu trả lời map y như `faster_whisper`: text đoạn bỏ khoảng trắng hai đầu, token từ giữ nguyên (kể cả khoảng trắng đầu), mốc thời gian, `probability`; từ chỉ có ở `words` cấp ngoài được gán vào đoạn chứa mốc bắt đầu của nó; tiến độ báo một lần khi xong (`done = total = duration`). `is_cloud` theo URL như VLM: private/LAN/Tailscale hoặc host trong `KNOWHOW_LOCAL_HOSTS` = local, host public khác = cloud (DataGuard chặn `factory_confidential` trước khi mở file audio). Cấu hình `KNOWHOW_ASR_*` (provider, model, device, compute_type, language, beam_size); `language` mặc định để trống = Whisper tự nhận ngôn ngữ từng file (tiếng Việt, tiếng Thái… đều được, lý do trích từ lời nào giữ nguyên ngôn ngữ đó); đặt giá trị để ép một ngôn ngữ — ép sai ngôn ngữ làm Whisper bịa câu (đo trên LASI: lời tiếng Thái ép `vi` ra câu tiếng Việt vô nghĩa). Model nạp lười, một lần mỗi process, dùng chung giữa các job. `knowhow video providers` liệt kê provider ASR, nơi chạy (`local`/`server`) và máy chủ đang dùng (URL không kèm mật khẩu, local/cloud).
  Phạm vi: chế độ `remote` dành cho **máy chủ suy luận của đội** (máy riêng của nhóm, khai báo host trong `KNOWHOW_LOCAL_HOSTS` nếu đi qua URL public như ngrok) — dùng khi demo; triển khai thực tế chạy local. Không làm chuỗi che dữ liệu/LeakGuard/audit của spec 01 FR-09b cho URL cloud: file audio/tài liệu không che được, và URL cloud không phải cách dùng dự kiến — ở URL cloud chỉ còn DataGuard (chặn `factory_confidential`).
- **FR-08** `align_transcript(segments, transcripts) -> dict[segment_id, list[TranscriptSegment]]` gán mỗi câu transcript vào đoạn có overlap thời gian lớn nhất (bằng nhau → đoạn trước; câu nằm ngoài mọi đoạn → đoạn gần nhất). Export ở `mentormind.capture.video` (spec 04 §3 import theo tên này).
- **FR-09** `VideoCapturePipeline`: probe → cắt (FR-03, fallback) → hậu xử lý → keyframe + clip → transcribe nếu `has_audio` → ghi `video.json`, `segments.json`, `transcript.json`; báo tiến độ từng giai đoạn qua callback; mỗi giai đoạn báo `done=0` ngay khi bắt đầu (cắt: trước khi dò cảnh/tay, `total=0` vì chưa biết số đoạn; transcribe: trước khi tách audio và nạp model ASR, `total` = thời lượng video) để giao diện không đứng ở giai đoạn trước. CLI (`knowhow video …`) và API (spec 08) gọi chung lớp này. Đọc video theo luồng; capture/model của một lần chạy được giải phóng khi xong (riêng model ASR giữ lại theo FR-07c).

## 6. Acceptance Criteria
- **AC-01** 3 video (video tổng hợp trong test, tới khi có `data/samples/video/`) → mỗi video ra ≥ 3 đoạn, mọi đoạn có 3 keyframe và 1 clip tồn tại trên đĩa.
- **AC-02** Không đoạn nào < 3s hoặc > 20s sau hậu xử lý.
- **AC-03** Các đoạn liên tiếp không chồng lấn và phủ ≥ 95% thời lượng video.
- **AC-04** `--method hand_activity` khi thiếu MediaPipe → tự rơi về `scene`, log cảnh báo, không crash.
- **AC-05** Video không có audio → `transcribe` trả list rỗng, không lỗi.
- **AC-06** `align_transcript` với dữ liệu giả lập: câu nằm vắt qua ranh giới được gán cho đoạn chứa phần lớn thời lượng của câu.
- **AC-07** Mọi `Segment` và `TranscriptSegment` mang đúng `data_classification` của `VideoAsset` gốc.
- **AC-08** `--recall-audio` với `--offset 12.5` trên audio giả lập → mọi `t_start` được cộng 12.5, `source="cued_recall"`; `--video-id` không tồn tại → báo lỗi, không ghi file.
- **AC-09** ASR provider cloud + `factory_confidential` → `ConfidentialDataError` trước khi mở file audio; tên provider chưa đăng ký → `ProviderConfigError` liệt kê tên có sẵn; hai lần `get_asr_provider` cùng cấu hình trả cùng một instance (model nạp một lần).
- **AC-10** Word timestamps giả lập → câu cắt ở dấu kết câu và ở quãng lặng ≥ 0.8 s; câu mang mốc của từ đầu/cuối.
- **AC-11** `hand_activity` với bộ dò tay giả lập: quãng nghỉ ≥ 0.4 s thành ranh giới, quãng nghỉ ngắn hơn thì không; `motion_score` của mọi đoạn trong [0, 1] và đoạn tay chạy nhanh có điểm cao hơn đoạn tay chậm.

- **AC-12** Bộ cắt raise lỗi bất kỳ khi chạy (không chỉ thiếu thư viện) → rơi xuống cách sau, log có lý do; `fixed_window` lỗi → lỗi được báo ra.
- **AC-13** `hand_activity` với bộ dò tay giả lập thấy tay ở 5% số khung → rơi về `scene`; thấy ở ≥ 10% → giữ `hand_activity`.
- **AC-14** `--recall-audio` chạy hai lần cùng `offset` → số câu `cued_recall` không đổi; bản ghi ở `offset` khác (khoảng không chồng) → câu cũ giữ nguyên; câu `inline` không bao giờ bị xoá.
- **AC-15** Pipeline với callback tiến độ: sự kiện đầu tiên là `("cut", 0, 0)`; sự kiện `transcribe` đầu tiên là `("transcribe", 0, thời lượng)` và đến trước khi provider ASR được dựng.
- **AC-16** Video có audio → lệnh ffmpeg của clip mã hóa audio AAC (không có `-an`); video câm → `-an`; clip có sẵn từ định dạng cũ (không có `clips/.format` đúng) được xuất lại, clip đúng định dạng và đúng ranh giới thì dùng lại.
- **AC-17** ASR `remote` (máy chủ giả lập): câu trả lời `verbose_json` → `ASRSegment`/`ASRWord` đúng từng giá trị (token thô giữ khoảng trắng đầu), `language`, `duration`; request multipart có `file`, `response_format=verbose_json`, `timestamp_granularities[]=word`, không có `language`/`model` khi tự nhận/mặc định, có khi đặt; tiến độ báo đúng một lần `(duration, duration)`; URL public không khai báo + `factory_confidential` → `ConfidentialDataError` trước khi mở file, không request; thiếu `KNOWHOW_INFERENCE_URL` → `ProviderConfigError` nêu tên biến; `knowhow video providers` liệt kê `remote`.

## 7. Tasks
- [x] T03-1 Models + `probe`.
- [x] T03-2 Cắt `scene` + `fixed_window` + hậu xử lý (AC-01..03).
- [x] T03-3 Keyframe + clip export.
- [x] T03-4 `hand_activity` với MediaPipe + fallback (AC-04, AC-11).
- [x] T03-5 `transcribe` faster-whisper + `align_transcript` (AC-05, AC-06, AC-10).
- [x] T03-6 Lan truyền `data_classification` (AC-07) + `--recall-audio` (AC-08).
- [x] T03-7 ASR provider `core.providers.asr` (`faster_whisper`, `fake`) + `knowhow video providers` (AC-09).
- [x] T03-8 `VideoCapturePipeline` + CLI `knowhow video`; gộp fallback của spec 04 vào `capture/video` (FR-09).
- [x] T03-9 Lấy từ nhánh `viethoang/video-capture`: fallback khi bộ cắt lỗi, ngưỡng thấy tay 10%, recall thay khoảng nó phủ, chặn PyAV khi import scenedetect (AC-12..AC-14).
- [x] T03-10 Báo `done=0` khi bắt đầu mỗi giai đoạn (FR-09, AC-15).
- [x] T03-11 Clip giữ tiếng khi video có audio; clip định dạng cũ được xuất lại (FR-06, AC-16).
- [x] T03-12 ASR provider `remote` trên máy chủ suy luận của đội (FR-07c, AC-17).

## Changelog
- v1.0 (23/9): khởi tạo.
- v1.1 (23/9): `Segment`/`TranscriptSegment` mang `data_classification`; thêm FR-07b nạp audio video-cued recall cho video câm (AC-07, AC-08, T03-6).
- v1.2 (27/9): đường dẫn module theo layout mới (bỏ `knowhow.`/`src/knowhow/`, xem spec 01 v1.3).
- v1.3 (06/10, Phúc): spec 03 làm đủ, chỉ CPU, theo thao tác của người (§4): `capture/video` (probe ffprobe, 3 cách cắt + chuỗi fallback, `motion_score` cho mọi cách, FR-04, keyframe, clip luôn re-encode H.264 để trình duyệt phát được và cắt đúng ranh giới, transcribe theo word timestamps, recall audio, `align_transcript`, `VideoCapturePipeline`, CLI `knowhow video`); ASR là provider `core.providers.asr` (FR-07c: `faster_whisper` CPU int8, `fake`); `hand_activity` dùng MediaPipe Tasks `HandLandmarker` (MediaPipe 1.0 bỏ API `solutions`), model ghim SHA-256; fallback tạm của spec 04 gộp vào đây. AC-09..AC-11, T03-7, T03-8. Extra `video` không cài `opencv-contrib-python` (override uv, xem `pyproject.toml`).
- v1.4 (06/10, Phúc): `KNOWHOW_VIDEO_METHOD` = cách cắt mặc định khi không chọn (FR-03).
- v1.5 (06/10, Phúc): FR-07 cắt câu không bao giờ giữa từ (tiếng Thái viết liền: "ครั|บ" trên LASI), dừng ở cuối mỗi đoạn nói của Whisper; ghép token giữ nguyên khoảng trắng của Whisper.
- v1.6 (07/10, Phúc): lấy 4 điểm từ nhánh `viethoang/video-capture` của Hoàng — FR-03 rơi xuống cách sau cả khi bộ cắt lỗi lúc chạy hoặc `hand_activity` thấy tay < 10% số khung, `scene` không nạp PyAV; FR-07b recall thay câu cũ trong khoảng nó phủ thay vì nối thêm (chạy lại từng nhân đôi câu). Luật "ít hơn 3 đoạn thì đổi cách" của nhánh đó không lấy: FR-04 đã chia đoạn > 20 s nên chỉ video rất ngắn mới < 3 đoạn. AC-12..AC-14, T03-9.
- v1.7 (07/10, Phúc): FR-09 mỗi giai đoạn báo `done=0` khi bắt đầu — trước đây giao diện đứng ở "Cắt đoạn 30/30" suốt lúc tách audio, nạp/tải model Whisper và nghe câu đầu. AC-15, T03-10.
- v1.8 (07/10, Phúc): FR-06 clip giữ tiếng (AAC) khi video có audio — trước đây bỏ audio nên trang duyệt không nghe được chuyên gia; `clips/.format` để clip câm cũ tự xuất lại. AC-16, T03-11.
- v1.9 (08/10, Phúc): FR-07c thêm ASR provider `remote` — Whisper trên máy chủ suy luận riêng của đội (`KNOWHOW_INFERENCE_URL`, dùng chung với Docling/bge-m3 của spec 02 v1.5), local/cloud theo URL như VLM; FR-07 "không dùng ASR cloud" thành "không dùng ASR của bên thứ ba". AC-17, T03-12.
- v1.10 (08/10, Phúc, review): FR-07c key VLM chỉ thay key trống khi cùng host; kết nối 10 s, file audio hết giờ chờ trả lời không gửi lại (spec 02 v1.6).
- v1.11 (08/10, Phúc): FR-07c ghi rõ phạm vi ASR `remote` (máy chủ của đội, khai báo local); không làm FR-09b cho URL cloud — chốt finding review remote-6/process-1.
