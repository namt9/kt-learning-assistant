# So sánh LLM thuần / Rule-based / Hybrid

> Sinh tự động bởi `python -m backend.app.evaluation.compare`. Không sửa tay.

- Dữ liệu: 30 bài nộp có nhãn đúng (`mutants.jsonl`), mỗi bài chạy qua mọi cấu hình bên dưới.
- LLM: claude:claude-sonnet-4-6.
- Precision / recall / F1 tính trên các mã lỗi có nhãn đúng; dòng đúng: chỉ ra dòng bị cài lỗi, lệch tối đa 1 dòng.

## Xác định lỗi

| Cấu hình | P | R | F1 | Đúng hoàn toàn | Dòng đúng | Mã ngoài danh mục |
|---|---|---|---|---|---|---|
| v0: công cụ thô | 0.60 | 0.81 | 0.69 | 37% | 53% | 5 |
| Rule-based | 0.97 | 0.79 | 0.87 | 63% | 53% | 5 |
| LLM thuần | 0.96 | 0.96 | 0.96 | 87% | 91% | 0 |
| Hybrid | 0.92 | 0.98 | 0.95 | 87% | 72% | 5 |

## Độ tin cậy và chi phí

| Cấu hình | Mã LLM bịa bị chặn | Lùi về luật | Lỗi LLM | Nghi lộ lời giải | Thời gian (trung vị / trung bình) |
|---|---|---|---|---|---|
| Rule-based | 0 | 0% | 0% | 0% | 0.0s / 0.0s |
| LLM thuần | 0 | 0% | 0% | 0% | 9.7s / 9.5s |
| Hybrid | 0 | 0% | 0% | 0% | 12.1s / 15.0s |

## Recall theo loại lỗi

| Lỗi | Số bài | v0: công cụ thô | Rule-based | LLM thuần | Hybrid |
|---|---|---|---|---|---|
| ASSIGN_IN_COND | 3 | 100% | 100% | 100% | 100% |
| DANGLING_PTR | 1 | 100% | 100% | 100% | 100% |
| DOUBLE_FREE | 1 | 100% | 100% | 100% | 100% |
| FORMAT_MISMATCH | 3 | 67% | 67% | 67% | 100% |
| INFINITE_LOOP | 10 | 70% | 70% | 90% | 100% |
| INT_OVERFLOW | 1 | 100% | 100% | 100% | 100% |
| MEM_LEAK | 1 | 100% | 100% | 100% | 100% |
| NULL_DEREF | 2 | 100% | 50% | 100% | 50% |
| OFF_BY_ONE | 9 | 44% | 44% | 100% | 100% |
| SCANF_MISSING_AMP | 9 | 100% | 100% | 100% | 100% |
| STRAY_SEMICOLON | 3 | 100% | 100% | 100% | 100% |
| SYNTAX_ERROR | 1 | 100% | 100% | 100% | 100% |
| UNDECLARED_ID | 1 | 100% | 100% | 100% | 100% |
| UNINIT_VAR | 2 | 100% | 100% | 100% | 100% |

## Đọc kết quả

- Hybrid = lỗi do công cụ kiểm chứng + lỗi LLM đề xuất thêm khi bài chưa đạt test (chỉ giữ nếu mã có trong KG và chỉ đúng dòng có thật). Recall Hybrid cao hơn Rule-based nhờ phần LLM đề xuất; LLM lỗi thì Hybrid lùi về Rule-based. Chất lượng giải thích: xem `docs/rubric_report.md`.
- "Nghi lộ lời giải" là kiểm tra tự động thô (từ 3 dòng trông như code trong lời giải thích); cần người đọc lại các trường hợp bị đánh dấu.
- Rule-based và Hybrid dùng luật khử nhiễu khai phá từ chính tập dữ liệu này, nên số đo trên đây lạc quan (đánh giá trên dữ liệu đã học). Số đo trên bài chưa thấy: xem phần leave-one-problem-out trong `docs/mining_report.md`.
- "Dòng đúng" so với dòng bị cài lỗi; công cụ thường báo dòng lỗi biểu hiện (ví dụ bỏ `= 0` ở dòng khai báo nhưng gcc báo ở dòng cộng dồn), nên chỉ số này thấp hơn thực tế.
- Lỗi do máy cài vào lời giải mẫu, chưa phải bài làm thật của sinh viên.
