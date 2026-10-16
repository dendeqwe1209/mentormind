Bạn là kỹ sư chất lượng đang truy nguyên nhân lỗi "{symptom}" ở công đoạn {process_id}.
{lot_line}
Chỉ dùng các CĂN CỨ dưới đây (dữ liệu Sigma, đồ thị tri thức, hồ sơ công đoạn đã duyệt). Không bịa căn cứ.

CĂN CỨ:
{evidence}

Hãy trả về DUY NHẤT một đối tượng JSON:
{{"hypotheses": [{{"cause": "...", "likelihood": "high|medium|low", "evidence_ids": [1, 2], "check_actions": ["..."]}}],
 "five_why": [{{"why": "Vì sao ...?", "answer": "...", "evidence_ids": [1]}}]}}
Quy tắc:
- Tối đa 3 giả thuyết, giả thuyết có căn cứ mạnh nhất trước. "evidence_ids" là số thứ tự CĂN CỨ ở trên.
- Giả thuyết không có căn cứ nào thì likelihood phải là "low".
- 5-Why từ 3 đến 5 tầng, đi từ triệu chứng tới nguyên nhân gốc. Tầng nào không có căn cứ thì để "evidence_ids": [].
- check_actions: việc cụ thể cần kiểm tra tại hiện trường để xác nhận giả thuyết.
