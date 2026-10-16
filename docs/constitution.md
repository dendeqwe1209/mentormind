# Constitution — Mentor Mind Know-How AI

Các điều khoản dưới đây áp dụng cho mọi spec, mọi task, mọi dòng code. Spec nào mâu thuẫn với constitution thì constitution thắng.

## Điều 1 — Spec là nguồn sự thật
Không có code nào tồn tại mà không truy ngược được về một Functional Requirement (`FR-xx`) trong một spec. Thay đổi hành vi = sửa spec trước, sửa code sau.

## Điều 2 — Bảo mật dữ liệu nhà máy (không thương lượng)
- Mọi nguồn dữ liệu mang nhãn `data_classification`: `public` | `synthetic` | `factory_confidential`.
- Dữ liệu `factory_confidential` **không bao giờ** được gửi tới provider có `is_cloud = True`. Việc này được chặn bằng code (`DataGuard`), không dựa vào kỷ luật con người.
- MVP 12/10 chỉ dùng dữ liệu `public` (Assembly101, IKEA ASM, MECCANO) và `synthetic` (video đội tự quay).
- Không commit video/audio thật. `.gitignore` chặn `data/raw/`, `data/factory/`, `*.mp4`, `*.wav` ngoài `data/samples/`.

## Điều 3 — Chuyên gia duyệt, AI không tự quyết
- Mọi `WorkProfile` do AI sinh ra có `status = draft`. Chỉ `approved` mới được nạp vào knowledge graph.
- Trường `reason` (lý do đằng sau thao tác) chỉ được điền từ lời chuyên gia (`reason_source ∈ {expert_verbal, expert_interview}`). VLM không được tự suy ra `reason`.

## Điều 4 — Luôn có căn cứ
Mọi câu trả lời của agent phải kèm citation (profile_id / document chunk / video segment). Không có căn cứ đủ mạnh → từ chối trả lời và gợi ý người cần hỏi.

## Điều 5 — Provider có thể hoán đổi
LLM, VLM, OCR, vector store đều đứng sau interface. Đổi từ API cloud sang self-host chỉ là đổi config, không sửa logic nghiệp vụ.

## Điều 6 — Chất lượng code
- Python 3.11, type hints đầy đủ, `mypy --strict` cho `core/schemas` và `core/guard`.
- Test bằng pytest; mỗi Acceptance Criteria có ít nhất 1 test. Test không gọi mạng thật (dùng fake provider).
- Mỗi module chạy độc lập được qua CLI `knowhow <module> <command>`.
- Cấu hình qua biến môi trường (`pydantic-settings`), không hardcode secret.

## Điều 7 — Phạm vi theo deadline
Deadline nộp bài: **12/10/2026**. Mọi yêu cầu được gắn MoSCoW. Hạng mục `Could` không được làm trước khi mọi `Must` xong.
