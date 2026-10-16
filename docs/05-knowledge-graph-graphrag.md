# 05 — Knowledge Graph & GraphRAG

**Owner:** Trung · **Tasks Excel:** S0-2, S1-5, S1-6, S2-3

## 1. Mục tiêu
Lưu tri thức đã duyệt dưới dạng đồ thị (quan hệ công đoạn – bước – linh kiện – lỗi – nguyên nhân – lô hàng) và cung cấp một retriever lai vector + graph để agent (spec 06) trả lời được cả câu hỏi mô tả lẫn câu hỏi quan hệ.

## 2. Graph schema (Neo4j 5)

**Nodes** (khóa duy nhất in đậm)
| Label | Thuộc tính |
|---|---|
| `Process` | **process_id**, name |
| `Step` | **profile_id**, step, step_order, hand_action, key_point, reason, reason_source, pass_criteria, confidence, version, reviewer, data_classification |
| `Exception` | **exception_id** (= profile_id + "#" + index), case, handling |
| `Part` | **part_number** |
| `Equipment` | **equipment_id** |
| `Expert` | **expert_id**, display_name |
| `Document` | **doc_id**, title, source_path |
| `VideoSegment` | **segment_id**, video_id, t_start, t_end |
| `Symptom` | **symptom_id** (= defect_code), name, data_classification |
| `RootCause` | **cause_id**, description, data_classification |
| `Lot` | **lot_id**, product_code, data_classification |

**Relationships**
```
(Process)-[:HAS_STEP {order}]->(Step)
(Step)-[:NEXT]->(Step)
(Step)-[:HAS_EXCEPTION]->(Exception)
(Step)-[:USES_PART]->(Part)
(Step)-[:ON_EQUIPMENT]->(Equipment)
(Expert)-[:CONTRIBUTED]->(Step)
(Step)-[:EVIDENCED_BY]->(VideoSegment)
(Step)-[:REFERENCES]->(Document)
(Lot)-[:PROCESSED_AT {date, shift, operator_id}]->(Process)
(Lot)-[:HAS_DEFECT {date, qty, data_classification}]->(Symptom)
(Symptom)-[:DETECTED_AT]->(Process)
(Symptom)-[:CAUSED_BY {confidence, source}]->(RootCause)
(RootCause)-[:PREVENTED_BY]->(Step)
```
`shift` là thuộc tính của `PROCESSED_AT`, không phải node riêng trong MVP. Dữ liệu Sigma mock chưa có `equipment_id` theo lô, nên đồ thị chỉ truy được lỗi theo lô/công đoạn; không được suy ra máy cụ thể gây lỗi từ thiết bị gắn với một Step. Câu hỏi “lỗi từng xảy ra ở máy nào khác” trong `architecture.md` cần dữ liệu thiết bị theo lô hoặc sự kiện trước khi hỗ trợ đáng tin cậy.
File `knowledge_base/kg/schema.cypher` chứa toàn bộ `CREATE CONSTRAINT ... IF NOT EXISTS` cho các khóa trên.

## 3. Loader — `knowledge_base.kg.loader`
- **FR-01** `load_profiles(profiles)` chỉ nhận `status == "approved"`; profile khác → bỏ qua và đếm vào `skipped`.
- **FR-02** Dùng `MERGE` theo khóa; chạy lại không nhân đôi node/cạnh. Khi `version` mới hơn → cập nhật thuộc tính.
- **FR-02b** Cạnh `EVIDENCED_BY` tạo từ `evidence.segment_ids` của profile (match theo `segment_id`), không suy ra bằng overlap thời gian.
- `evidence.t_start/t_end` là khoảng của profile và được lưu trên cạnh `EVIDENCED_BY` (`profile_t_start/profile_t_end`); không ghi đè mốc thật của node `VideoSegment` khi nhiều profile dùng chung segment.
- **FR-03** `NEXT` được tính lại cho cả process sau mỗi lần nạp, theo `step_order`, dùng `profile_id` để phá hòa khi thứ tự trùng.
- **FR-04** `unload_profile(profile_id)` xóa `Step` và cạnh liên quan (dùng khi profile bị reject sau khi đã approved).
- **FR-05** `load_sigma(adapter, classification)` nạp `Lot`, `PROCESSED_AT`, `HAS_DEFECT`, `Symptom`, `CAUSED_BY`, `PREVENTED_BY` từ Sigma adapter (spec 07).
- `classification` là nhãn của nguồn Sigma (constitution Điều 2), mặc định `factory_confidential` (fail-closed), ghi lên `Lot`, `HAS_DEFECT`, `Symptom`, `RootCause`. Mock CSV của spec 07 §3 là `synthetic` nên nạp bằng `--classification synthetic`; template không được gán cứng nhãn.
- Nếu Sigma được nạp trước profile, giữ `prevention_profile_id` trên `RootCause` và chỉ tạo `PREVENTED_BY` khi Step tương ứng đã approved; nạp profile sau đó phải nối cạnh này.
- **FR-06** Profile approved cũng được upsert vào vector store (pgvector, qua `VectorStore`) như một chunk (`source_type="work_profile"`, text = step + hand_action + key_point + reason + exceptions) để tìm được bằng vector. `unload_profile` xóa luôn chunk này.
- CLI: `knowhow kg init` (chạy schema.cypher), `knowhow kg load-profiles`, `knowhow kg load-sigma [--classification]`, `knowhow kg stats`.

## 4. Retriever — `knowledge_base.retrieval.hybrid`
```python
class Citation(BaseModel):
    source_type: Literal["work_profile", "document", "video_segment", "sigma"]
    ref_id: str
    snippet: str
    score: float | None = None


class RetrievedContext(BaseModel):
    query: str
    process_id: str | None
    passages: list[str]  # đoạn văn bản đưa vào prompt
    graph_facts: list[str]  # câu dạng "Bước X dùng linh kiện Y"
    citations: list[Citation]
    classifications: list[DataClassification]


class HybridRetriever:
    def retrieve(self, query: str, process_id: str | None = None, k: int = 8) -> RetrievedContext: ...
```
`passages[i]` luôn có nguồn tại `citations[i]` và nhãn nhạy cảm tại `classifications[i]`; agent dùng nhãn này để lọc trước khi gửi context tới provider cloud. Cùng một document có thể đóng góp nhiều chunk và nhiều citation cùng `ref_id`.
Citation Sigma về lô dùng `lot_id`; fact nguyên nhân từ catalog dùng `ref_id="defect_catalog.csv#<defect_code>"` để phân biệt nguồn catalog với bản ghi lô.
Nhãn của một fact graph = nhãn khắt khe nhất trong các node/cạnh tạo nên nó (vd. `Lot` + `HAS_DEFECT` + `Symptom`); thiếu nhãn → `factory_confidential`.
Thuật toán:
1. **Vector**: tìm top-k trong pgvector — hybrid gồm dense (cosine trên cột `embedding`, index HNSW) + lexical (`ts_rank` trên `tsvector` cấu hình `simple` + `unaccent`, vì Postgres không có từ điển tiếng Việt), gộp bằng Reciprocal Rank Fusion (k=60); filter `process_id` nếu có.
   PG backend dùng BGE-M3 local qua extra `kg-semantic` (`uv sync --extra kg --extra kg-semantic`); model phải nằm trong cache local trước khi chạy offline. Mọi chunk PostgreSQL mang `metadata.embedding_model` và truy vấn chỉ ghép vector cùng model, tránh trộn không gian embedding.
2. **Graph expansion**: với hit `work_profile` → lấy `Step` + bước trước/sau (`NEXT`), `Exception`, `Part`, `Expert`, `VideoSegment`; với hit `document` → các `Step` có `REFERENCES` tới document đó.
3. **Relational intent**: một router LLM chạy local/self-host (output JSON enum) chọn 0..1 template Cypher trong bảng dưới. **Không sinh Cypher tự do** (an toàn + ổn định). Nếu router cấu hình cloud, bỏ qua routing để không gửi câu hỏi nhà máy ra ngoài.
4. Gộp, khử trùng, xếp hạng (vector score + bonus 0.1 cho node chạm bởi graph), cắt theo ngân sách 3.000 token. Node chạm bởi graph = hit vector có expansion trả về dữ liệu, hoặc node có trong kết quả expansion/template. Fact mở rộng từ một hit mang điểm của hit đó và xếp ngay sau hit (không bao giờ vượt passage gốc); fact chỉ đến từ template = 0 + 0.1. Trùng (`source_type`, `ref_id`, nội dung) → giữ điểm cao nhất.

| Template | Tham số | Ví dụ câu hỏi |
|---|---|---|
| `steps_of_process` | process_id | "Công đoạn PACK01 gồm những bước nào?" |
| `steps_using_part` | part_number | "Linh kiện A123 được thao tác ở bước nào?" |
| `where_symptom_occurred` | symptom text | "Lỗi móp góc từng xảy ra ở lô/công đoạn nào?" |
| `root_causes_of_symptom` | symptom text | "Nguyên nhân thường gặp của lỗi thiếu linh kiện?" |
| `prevention_steps` | symptom text | "Bước nào giúp tránh lỗi này?" |
| `lots_with_defect` | defect_code, date range | "Lô nào bị lỗi D-03 tuần trước?" |

Symptom text → `symptom_id`: chuẩn hóa cả câu hỏi lẫn `Symptom.name` (lowercase, bỏ dấu tiếng Việt bằng `unicodedata` NFD, đổi `đ`→`d`), rồi so khớp mờ bằng Python (`rapidfuzz.fuzz.token_set_ratio ≥ 70`, lấy điểm cao nhất) trên danh sách Symptom lấy từ graph (catalog nhỏ, D-01..D-06). Không khớp → fallback full-text index trên `Symptom.name` (tạo trong schema.cypher); text được viết thường và escape ký tự đặc biệt của Lucene trước khi truy vấn. Vẫn không có → template trả rỗng, retriever chỉ dùng vector + expansion.

Router: output validate bằng Pydantic (`template: Literal[...] | None`, tham số theo từng template). Output sai schema, router lỗi (timeout, lỗi kết nối: `ProviderError`) hoặc template trả 0 dòng → bỏ qua bước relational, không raise. `process_id` do caller truyền phải áp dụng cho cả vector và graph; router không được nới phạm vi này.

## 5. Acceptance Criteria
- **AC-01** Nạp 5 profile (3 approved, 1 draft, 1 rejected) → graph có đúng 3 `Step`, `skipped = 2`.
- **AC-02** Nạp lại cùng dữ liệu → số node/cạnh không đổi.
- **AC-03** `NEXT` nối đúng thứ tự `step_order` 1→2→3.
- **AC-04** `unload_profile` → `Step` và các cạnh của nó biến mất, node `Part` dùng chung vẫn còn.
- **AC-05** Câu "Lỗi thiếu linh kiện từng xảy ra ở lô nào?" trên dữ liệu seed → router chọn `where_symptom_occurred`, kết quả chứa đúng các `lot_id` trong fixture.
- **AC-06** Mọi `passage` trong `RetrievedContext` có ít nhất một `Citation` tương ứng.
- **AC-07** Router nhận câu không liên quan quan hệ → không chọn template nào (chỉ vector + expansion).
- **AC-08** Mỗi template trong 6 template có ít nhất 1 integration test trên dữ liệu seed (Sigma mock + profile fixture), kết quả khớp giá trị kỳ vọng ghi trong test.
- **AC-09** Symptom text gõ không dấu ("thieu linh kien") → map đúng `D-01`.
- **AC-10** Router (FakeLLM) trả JSON sai schema, tên template không tồn tại, symptom text chứa cú pháp Lucene, hoặc router lỗi kết nối → `retrieve` vẫn trả kết quả vector + expansion, không raise.
- **AC-11** Fact Sigma mang nhãn của nguồn được nạp (`load_sigma(..., classification)`); fact ghép từ node thiếu nhãn hoặc nhãn khác nhau → nhãn khắt khe nhất, mặc định `factory_confidential`.
- Test AC-01..04 và AC-08 chạy trên Neo4j thật (`@pytest.mark.integration`); AC-05..07, AC-09..11 có bản unit với fake graph client.

## 6. Tasks
- [x] T05-1 `schema.cypher` + `kg init`.
- [x] T05-2 Loader profiles (AC-01..04) + đẩy chunk profile vào pgvector (FR-06).
- [x] T05-3 Loader Sigma (FR-05) với CSV adapter mock đọc-only.
- [x] T05-4 Vector search + graph expansion.
- [x] T05-5 Router + 6 template Cypher + khớp symptom không dấu (AC-05, AC-07, AC-09, AC-10).
- [ ] T05-7 Integration test cho đủ 6 template trên seed (AC-08).
- [x] T05-6 Gộp/xếp hạng/ngân sách token + citation (AC-06).

Integration test T05-7 đã viết và được đánh dấu `integration`; cần chạy với `KNOWHOW_TEST_NEO4J_URI` trỏ tới Neo4j 5 dùng riêng cho test. Môi trường không có dịch vụ sẽ skip. Bộ fixture `data/mock_sigma/` hiện là 6 lô synthetic tối thiểu phục vụ graph; quy mô 50 lô và generator thuộc spec 07.

## Changelog
- v1.0 (23/9): khởi tạo.
- v1.1 (23/9): sửa ví dụ `D-07` → `D-03` (catalog spec 07 chỉ có D-01..D-06); FR-02b tạo `EVIDENCED_BY` từ `evidence.segment_ids`.
- v1.2 (24/9): symptom matching bỏ dấu + fuzzy trên catalog, full-text làm fallback; router validate Pydantic, lỗi → bỏ qua relational; test đủ 6 template (AC-08..10, T05-7).
- v1.3 (27/9): vector store đổi Milvus → pgvector; hybrid = dense + full-text `simple`/`unaccent`, gộp RRF (FR-06, thuật toán bước 1, T05-2).
- v1.4 (27/9): đường dẫn module theo layout mới (bỏ `knowhow.`/`src/knowhow/`, xem spec 01 v1.3).
- v1.5 (02/10): rà soát với PRD/BRD và code; làm rõ reviewer/classification, thứ tự NEXT, citation theo passage, process filter, router local, và trạng thái triển khai.
- v1.6 (02/10, review): nhãn Sigma theo nguồn — `load_sigma(adapter, classification)`, CLI `--classification` mặc định `factory_confidential`, fact lấy nhãn khắt khe nhất, bỏ `'synthetic'` gán cứng trong template (FR-05, §4, AC-11); router lỗi kết nối → bỏ qua relational (AC-10); full-text symptom escape Lucene (AC-10); làm rõ xếp hạng bước 4 (fact không vượt passage gốc, hit được graph chạm +0.1).
