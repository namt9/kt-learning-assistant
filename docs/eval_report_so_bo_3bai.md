# So sánh LLM thuần / Rule-based / Hybrid

> Sinh tự động bởi `python -m backend.app.evaluation.compare`. Không sửa tay.

- Dữ liệu: 30 bài nộp có nhãn đúng (`mutants.jsonl`), mỗi bài chạy qua mọi cấu hình bên dưới.
- LLM: ollama:qwen2.5:7b-instruct.
- Precision / recall / F1 tính trên các mã lỗi có nhãn đúng; dòng đúng: chỉ ra dòng bị cài lỗi, lệch tối đa 1 dòng.

## Xác định lỗi

| Cấu hình | P | R | F1 | Đúng hoàn toàn | Dòng đúng | Mã ngoài danh mục |
|---|---|---|---|---|---|---|
| v0: công cụ thô | 0.59 | 0.84 | 0.69 | 30% | 61% | 4 |
| Rule-based | 0.93 | 0.84 | 0.88 | 67% | 61% | 4 |
| LLM thuần | 0.38 | 0.45 | 0.41 | 23% | 41% | 0 |
| Hybrid | 0.93 | 0.84 | 0.88 | 67% | 61% | 4 |

## Độ tin cậy và chi phí

| Cấu hình | Mã LLM bịa bị chặn | Lùi về luật | Lỗi LLM | Nghi lộ lời giải | Thời gian (trung vị / trung bình) |
|---|---|---|---|---|---|
| Rule-based | 0 | 0% | 0% | 0% | 0.0s / 0.0s |
| LLM thuần | 0 | 0% | 0% | 0% | 156.5s / 157.0s |
| Hybrid | 0 | 3% | 0% | 0% | 121.1s / 127.2s |

## Recall theo loại lỗi

| Lỗi | Số bài | v0: công cụ thô | Rule-based | LLM thuần | Hybrid |
|---|---|---|---|---|---|
| ASSIGN_IN_COND | 2 | 100% | 100% | 100% | 100% |
| DANGLING_PTR | 2 | 100% | 100% | 50% | 100% |
| DOUBLE_FREE | 2 | 100% | 100% | 100% | 100% |
| FORMAT_MISMATCH | 4 | 75% | 75% | 75% | 75% |
| INFINITE_LOOP | 6 | 50% | 50% | 33% | 50% |
| INT_DIVISION | 1 | 100% | 100% | 100% | 100% |
| INT_OVERFLOW | 3 | 67% | 67% | 0% | 67% |
| MEM_LEAK | 1 | 100% | 100% | 0% | 100% |
| MISSING_BRACES | 2 | 100% | 100% | 0% | 100% |
| NULL_DEREF | 2 | 100% | 100% | 0% | 100% |
| OFF_BY_ONE | 4 | 25% | 25% | 75% | 25% |
| SCANF_MISSING_AMP | 8 | 100% | 100% | 0% | 100% |
| STRAY_SEMICOLON | 6 | 100% | 100% | 33% | 100% |
| UNDECLARED_ID | 1 | 100% | 100% | 100% | 100% |
| UNINIT_VAR | 5 | 100% | 100% | 100% | 100% |

## Đọc kết quả

- Rule-based và Hybrid xác định lỗi giống nhau (cùng tầng luật); khác nhau ở chất lượng giải thích, cần chấm thêm theo rubric (LLM-as-judge + người chấm).
- "Nghi lộ lời giải" là kiểm tra tự động thô (từ 3 dòng trông như code trong lời giải thích); cần người đọc lại các trường hợp bị đánh dấu.
- Rule-based và Hybrid dùng luật khử nhiễu khai phá từ chính tập dữ liệu này, nên số đo trên đây lạc quan (đánh giá trên dữ liệu đã học). Số đo trên bài chưa thấy: xem phần leave-one-problem-out trong `docs/mining_report.md`.
- "Dòng đúng" so với dòng bị cài lỗi; công cụ thường báo dòng lỗi biểu hiện (ví dụ bỏ `= 0` ở dòng khai báo nhưng gcc báo ở dòng cộng dồn), nên chỉ số này thấp hơn thực tế.
- Lỗi do máy cài vào lời giải mẫu, chưa phải bài làm thật của sinh viên.
