# So sánh LLM thuần / Rule-based / Hybrid

> Sinh tự động bởi `python -m backend.app.evaluation.compare`. Không sửa tay.

- Dữ liệu: 270 bài nộp có nhãn đúng (`mutants.jsonl`), mỗi bài chạy qua mọi cấu hình bên dưới.
- LLM: không có.
- Precision / recall / F1 tính trên các mã lỗi có nhãn đúng; dòng đúng: chỉ ra dòng bị cài lỗi, lệch tối đa 1 dòng.

## Xác định lỗi

| Cấu hình | P | R | F1 | Đúng hoàn toàn | Dòng đúng | Mã ngoài danh mục |
|---|---|---|---|---|---|---|
| v0: công cụ thô | 0.60 | 0.79 | 0.68 | 33% | 54% | 33 |
| Rule-based | 0.95 | 0.76 | 0.84 | 55% | 54% | 33 |

## Độ tin cậy và chi phí

| Cấu hình | Mã LLM bịa bị chặn | Lùi về luật | Lỗi LLM | Nghi lộ lời giải | Thời gian (trung vị / trung bình) |
|---|---|---|---|---|---|
| Rule-based | 0 | 0% | 0% | 0% | 0.0s / 0.0s |

## Recall theo loại lỗi

| Lỗi | Số bài | v0: công cụ thô | Rule-based |
|---|---|---|---|
| ARRAY_OOB | 5 | 100% | 20% |
| ASSIGN_IN_COND | 13 | 100% | 100% |
| DANGLING_PTR | 15 | 80% | 80% |
| DOUBLE_FREE | 15 | 40% | 40% |
| FORMAT_MISMATCH | 26 | 96% | 96% |
| INFINITE_LOOP | 90 | 66% | 66% |
| INT_DIVISION | 9 | 100% | 100% |
| INT_OVERFLOW | 8 | 62% | 62% |
| MEM_LEAK | 13 | 69% | 62% |
| MISSING_BRACES | 8 | 100% | 100% |
| NULL_DEREF | 12 | 100% | 75% |
| OFF_BY_ONE | 83 | 45% | 45% |
| SCANF_MISSING_AMP | 104 | 100% | 100% |
| STRAY_SEMICOLON | 22 | 100% | 100% |
| SYNTAX_ERROR | 3 | 100% | 100% |
| UNDECLARED_ID | 8 | 100% | 100% |
| UNINIT_VAR | 27 | 100% | 74% |

## Đọc kết quả

- Rule-based và Hybrid xác định lỗi giống nhau (cùng tầng luật); khác nhau ở chất lượng giải thích, cần chấm thêm theo rubric (LLM-as-judge + người chấm).
- "Nghi lộ lời giải" là kiểm tra tự động thô (từ 3 dòng trông như code trong lời giải thích); cần người đọc lại các trường hợp bị đánh dấu.
- Rule-based và Hybrid dùng luật khử nhiễu khai phá từ chính tập dữ liệu này, nên số đo trên đây lạc quan (đánh giá trên dữ liệu đã học). Số đo trên bài chưa thấy: xem phần leave-one-problem-out trong `docs/mining_report.md`.
- "Dòng đúng" so với dòng bị cài lỗi; công cụ thường báo dòng lỗi biểu hiện (ví dụ bỏ `= 0` ở dòng khai báo nhưng gcc báo ở dòng cộng dồn), nên chỉ số này thấp hơn thực tế.
- Lỗi do máy cài vào lời giải mẫu, chưa phải bài làm thật của sinh viên.
