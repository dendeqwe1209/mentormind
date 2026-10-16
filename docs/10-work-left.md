# 10 — Công việc còn lại đến MVP 12/10/2026

**Owner:** Trung · **Ảnh chụp trạng thái:** 04/10/2026, nhánh `main` @ `da08a2e` · **Còn lại:** 8 ngày

> Tài liệu trạng thái, không phải spec: không thêm FR mới. Đối chiếu [architecture](architecture.md),
> [BRD](BRD.md), [PRD](PRD.md), [README](../README.md) và mục **Tasks** của spec 01–09 với code thật
> trên `main` và trên các nhánh chưa merge. Khi checkbox trong spec lệch với code, tài liệu này ghi
> theo code. Cách kiểm thử từng hạng mục: [test-guide.md](test-guide.md).

## 1. Tóm tắt

- `make check` xanh trên `main`: ruff, mypy, **274 test pass, 1 skip** (test integration Neo4j, chỉ chạy
  khi có `KNOWHOW_TEST_NEO4J_URI`).
- `make demo` **chưa chạy được**. Preflight của `scripts/demo.sh` thiếu 6/9 lệnh (`sigma gen-mock`,
  `ingest run`, `ingest index`, `video segment`, `agent ask`, `agent rca`) và file
  `data/samples/review_decisions.json`.
- Khoảng một nửa phần còn thiếu **đã được viết**, đang nằm trên 2 nhánh chưa merge (spec 02, 06, 09).
- **Spec 03 (video) chưa bắt đầu**: không có code, không có nhánh. Đây là đường găng: không có
  transcript thì `reason` luôn null, nên bước "Vì sao?" của demo và chỉ số
  `reason_coverage.synthetic ≥ 60%` (spec 09) không đạt được.
- Dữ liệu mẫu (3–5 case PACK01) và golden set 30 câu chưa có trên nhánh nào.

## 2. Trạng thái theo spec

| Spec | Checkbox | Thực tế trong code | Còn lại | Owner (PRD §13) |
|---|---|---|---|---|
| 01 Scaffold | 7/7 | Xong | — | Trung |
| 02 Ingest/OCR | 0/6 | Code + test nằm trên nhánh `viethoang/ingext-index-trungntresolve` (Docling/mmore, chunker, `ingest run/index`, pgvector, bge-m3) | Gỡ 5 conflict, merge, tick T02-1…T02-6 | Việt Hoàng |
| 03 Video | 0/6 | **Chưa có gì**, `mentormind/capture/` rỗng | T03-1…T03-6 | Việt Hoàng |
| 04 VLM | 11/11 | Xong; `describe` và `propose-reasons` đã ghi vào profile store | `propose-reasons` cần `transcript_excerpt` từ spec 03 | Phúc |
| 05 KG/GraphRAG | 6/7 | Loader, router, 6 template, hybrid retrieval xong | T05-7: test đủ 6 template đã viết (`tests/knowledge_base/test_graph_retrieval.py:481`) nhưng luôn bị skip. Cần chạy trên Neo4j thật (`make up`), ghi kết quả rồi tick | Việt Hoàng / Trung |
| 06 Agents | 1/4 | T06-2…T06-4 nằm trên nhánh `phuc-nguyen/agents-eval-on-main`. Trên `main`, `/assistant/ask` và `/rca/investigate` trả câu trả lời mock viết cứng | Merge nhánh | Phúc |
| 07 Sigma | 0/3 | T07-1 thực tế đã xong (`knowledge_base/sigma/adapter.py`: model, Protocol, `LotNotFound`, `CsvSigmaAdapter`); CSV mock có trong `data/mock_sigma/` | T07-2 `scripts/gen_mock_sigma.py` (seed 42); T07-3 lệnh `knowhow sigma` (nhóm lệnh đang rỗng); test AC-01…06 | Vinh |
| 08 API/UI | 0/6 | T08-1 profile store + test xong; router của T08-2…T08-4 đã có, AC-01…04 và AC-06 có test; UI React/Vite 3 tab | Nối router vào agent thật; spec ghi Streamlit (T08-5, FR-05) nhưng code là React, cần sửa spec; T08-6 `demo.sh` + `review_decisions.json` | Vinh |
| 09 Evaluation | 0/4 | Validator, Ragas runner, `review-stats`, `report` nằm trên nhánh `phuc-nguyen/agents-eval-on-main` | Merge; viết nội dung `data/golden_set/qa.jsonl` | Đạt / Phúc |

## 3. Nhánh chưa merge

| Nhánh | Nội dung | Merge vào `main` |
|---|---|---|
| `phuc-nguyen/agents-eval-on-main` (6 commit, 04/10) | Spec 06 + spec 09, khoảng 4 900 dòng | Sạch, không conflict |
| `viethoang/ingext-index-trungntresolve` (5 commit, 03/10) | Spec 02 + tài liệu mẫu `data/samples/docs/` | 5 conflict: `mentormind/core/cli.py`, `mentormind/knowledge_base/store/vector_store.py`, `tests/knowledge_base/store/test_vector_store.py`, `pyproject.toml`, `uv.lock` |

**Quyết định cần chốt trước khi merge nhánh thứ hai.** `main` có `store/pgvector.py` + `store/embedding.py`
(từ PR #9 graphrag). Nhánh ingest xóa hai file đó và thay bằng `store/pgvector_store.py` + `store/embedder.py`.
Chỉ giữ **một** bản. Hiện `vector_store.py:152` và `tests/knowledge_base/store/test_vector_store.py` đang
import bản của `main`.

**Đặt tên trường cần kiểm khi merge nhánh agents.** Spec 06 và `AssistantAnswer` của agent dùng
`suggested_contact`; schema API (`core/schemas/api.py`) và UI dùng `suggested_expert`. Nhánh của Phúc đã
ánh xạ hai tên ở `mentormind/agents/api.py:67`.

**Nhánh có thể đóng** (xác nhận với người sở hữu trước khi xóa):
- Đã nằm trong hai nhánh trên: `phuc-nguyen/agents-on-main`, `viethoang/ingest-index`.
- Đã được thay bằng bản `*-on-main`: `phuc-nguyen/spec06-agents`, `phuc-nguyen/spec09-evaluation`,
  `phuc-nguyen/vlm-provider-stack`.
- Đã vào `main`: `phuc-nguyen/restructure-repo-layout`, `fix/review-findings`, `dendeqwe1209-BRD-PRD`,
  `vinh/feat-api-ui`, `trungnt/graphrag`.

## 4. Dữ liệu mẫu và deliverable BA (PRD §6, §7)

| Hạng mục | Đường dẫn | Trạng thái |
|---|---|---|
| SOP, bản vẽ scan, XLSX mẫu (spec 02 AC-01) | `data/samples/docs/` | Có trên nhánh ingest; trên `main` chỉ có `data/demo/packing/packing_sop.pdf` |
| 3–5 case PACK01: C1 đủ bằng chứng, C2 video câm, C3 ngoại lệ, C4 mơ hồ, C5 mâu thuẫn | `data/samples/packing/case_00x/` (PRD §5.2) | Chưa có |
| Video demo + lời chuyên gia (`packing_demo_01.mp4`, `expert_comment_01.wav`) | `data/samples/video/` (`demo.sh`, spec 03 AC-01 cần 3 video) | Chưa có. Video public LASI chỉ có ground truth `data/video/groundtruth.json` |
| Quyết định duyệt mẫu (mô phỏng chuyên gia) | `data/samples/review_decisions.json` | Chưa có, nên demo dừng ở preflight |
| Golden set ≥ 30 câu: how 10, why 6, exception 5, relational 5, out_of_scope 4 | `data/golden_set/qa.jsonl` | Chưa có; validator đã có trên nhánh của Phúc |
| Sigma mock | `data/mock_sigma/*.csv` | Có; chưa có script sinh lại (T07-2) |

`.gitignore` cho phép video/audio chỉ trong `data/samples/` (constitution Điều 2).

## 5. Đối chiếu tiêu chí nghiệm thu MVP

### PRD §12

| AC | Nội dung | Trạng thái | Còn chặn bởi |
|---|---|---|---|
| PRD-AC-01 | `make demo` offline chạy end-to-end | ❌ | CLI spec 02/03/06/07, `review_decisions.json` |
| PRD-AC-02 | Video câm không sinh `reason` | ✅ Schema + lượt A–C (spec 04 AC-02, spec 01 AC-04) | — |
| PRD-AC-03 | Chỉ profile approved tìm được | 🟡 Có code và unit test (spec 05 AC-01); chưa kiểm end-to-end | Demo |
| PRD-AC-04 | Có citation; thiếu bằng chứng thì từ chối | 🟡 Nằm trên nhánh agents | Merge |
| PRD-AC-05 | DataGuard chặn dữ liệu mật khỏi cloud | ✅ Spec 01 AC-05, spec 04 AC-03/13/16/17 | — |
| PRD-AC-06 | Báo cáo evaluation đủ chỉ số + run metadata | 🟡 Code nằm trên nhánh agents | Merge + golden set |
| PRD-AC-07 | Truy được reviewer từ UI/API/lịch sử | 🟡 Profile store và API có `review`; chưa kiểm trên UI | — |
| PRD-AC-08 | Trace raw → segment/chunk → profile → citation → answer | ❌ | Spec 03 |

### Must của product overview §4

| Must | Trạng thái |
|---|---|
| M1 Ingest tài liệu (spec 02) | 🟡 Trên nhánh, chờ merge |
| M2 Cắt video + keyframe (spec 03) | ❌ Chưa bắt đầu |
| M3 VLM sinh WorkProfile nháp (spec 04) | ✅ |
| M4 UI duyệt approve/reject/edit (spec 08) | 🟡 Có UI và API; text còn tiếng Anh, chưa chạy trên dữ liệu thật |
| M5 Graph + vector, truy vấn hybrid (spec 05) | ✅ Code xong; integration chưa chạy |
| M6 Work Assistant có citation (spec 06) | 🟡 Trên nhánh, chờ merge |
| M7 Ragas trên golden set + báo cáo (spec 09) | 🟡 Code trên nhánh; thiếu golden set |
| M8 `make demo` toàn luồng | ❌ |

## 6. Dọn dẹp và lệch tài liệu

- `mentormind/core/schemas.py` là file chết: Python luôn import package `mentormind/core/schemas/`,
  file này không bao giờ được nạp. Nên xóa để không ai sửa nhầm.
- Checkbox lệch code: T07-1 và T08-1…T08-4 đã có code nhưng chưa tick; T05-7 đã viết test nhưng chưa
  chạy lần nào.
- Spec 08 T08-5 và FR-05 ghi Streamlit, trong khi UI thật là React/Vite (`mentormind/frontend/`). Theo
  constitution Điều 1, spec phải được sửa trước.
- UI còn nhiều text tiếng Anh hiển thị cho người dùng (ví dụ `ReviewProfilesTab.tsx:121`, `:268`, `:473`;
  `AssistantTab.tsx:84`, `:104`, `:289`; `RcaTab.tsx:87`). CLAUDE.md và PRD NFR-06 yêu cầu tiếng Việt.
- Câu hỏi mở chưa chốt dù hạn là 25/9 (`00-product-overview.md` §6): BTC yêu cầu nộp gì ngày 12/10; có
  chuyên gia thật ghi âm không. S4 (self-host Qwen3-VL) vẫn chờ Đạt xác nhận. BRD §13 còn 6 mục TBD.

## 7. Kế hoạch đề xuất 8 ngày

| Ngày | Việc | Người |
|---|---|---|
| 04–05/10 | Merge `agents-eval-on-main`; chốt bản pgvector, gỡ conflict, merge nhánh ingest; đóng nhánh cũ | Phúc, Việt Hoàng, Trung |
| 04–07/10 | Spec 03 bản tối thiểu: T03-1, T03-2 (`scene` + `fixed_window`), T03-3, T03-5, T03-6. Nếu hết giờ, T03-4 (MediaPipe) dùng fallback `scene` theo AC-04 | Việt Hoàng (+ người hỗ trợ) |
| 04–07/10 | Case C1–C5, video + lời chuyên gia, `review_decisions.json`, golden set 30 câu | Đạt |
| 05–06/10 | Spec 07 T07-2, T07-3; nối `/assistant` và `/rca` vào agent thật, bỏ mock; Việt hóa UI | Vinh |
| 06/10 | Chạy T05-7 trên Neo4j thật; sửa spec 08 (React); xóa `core/schemas.py` | Trung |
| 08–09/10 | `make demo` end-to-end offline trên máy sạch; sửa lỗi | Cả đội |
| 10/10 | `knowhow eval` với judge mạnh + `report`; đóng băng code | Phúc, Đạt |
| 11/10 | Tổng duyệt demo ≤ 5 phút; slide và video | Cả đội |
| 12/10 | Nộp | — |

## 8. Không làm trước 12/10

Constitution Điều 7: chưa xong mọi Must thì không làm Could.

- Agent phỏng vấn 5-Why (architecture, Lớp 1): chưa có spec.
- Camera AI, Sigma thật, SSO, triển khai production (BRD §8.2).
- Hạng mục Could: A3/8D PDF, video nhiều góc, dashboard đóng góp chuyên gia.
- Mốc "chạy 3–5 video thật trên GPU tự host" (architecture §8) là mốc trước khi tổng kết dự án, không
  phải điều kiện của bản nộp 12/10.

## Changelog
- v1.0 (04/10/2026): ảnh chụp trạng thái đầu tiên, đối chiếu `main` @ `da08a2e` với các nhánh chưa merge.
