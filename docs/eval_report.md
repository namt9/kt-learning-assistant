# So sánh LLM thuần / Rule-based / Hybrid

> Sinh tự động bởi `python -m backend.app.evaluation.compare`. Không sửa tay.

- Dữ liệu: 3 bài nộp có nhãn đúng (`mutants.jsonl`), mỗi bài chạy qua mọi cấu hình bên dưới.
- LLM: ollama:qwen2.5:7b-instruct.
- Precision / recall / F1 tính trên các mã lỗi có nhãn đúng; dòng đúng: chỉ ra dòng bị cài lỗi, lệch tối đa 1 dòng.

## Xác định lỗi

| Cấu hình | P | R | F1 | Đúng hoàn toàn | Dòng đúng | Mã ngoài danh mục |
|---|---|---|---|---|---|---|
| v0: công cụ thô | 0.50 | 1.00 | 0.67 | 0% | 75% | 0 |
| Rule-based | 0.80 | 1.00 | 0.89 | 67% | 75% | 0 |
| LLM thuần | 0.33 | 0.50 | 0.40 | 33% | 25% | 0 |
| Hybrid | 0.80 | 1.00 | 0.89 | 67% | 75% | 0 |

## Độ tin cậy và chi phí

| Cấu hình | Mã LLM bịa bị chặn | Lùi về luật | Lỗi LLM | Nghi lộ lời giải | Thời gian (trung vị / trung bình) |
|---|---|---|---|---|---|
| Rule-based | 0 | 0% | 0% | 0% | 0.0s / 0.0s |
| LLM thuần | 0 | 0% | 0% | 0% | 136.3s / 133.3s |
| Hybrid | 0 | 0% | 0% | 0% | 112.1s / 118.3s |

## Recall theo loại lỗi

| Lỗi | Số bài | v0: công cụ thô | Rule-based | LLM thuần | Hybrid |
|---|---|---|---|---|---|
| DOUBLE_FREE | 1 | 100% | 100% | 100% | 100% |
| SCANF_MISSING_AMP | 1 | 100% | 100% | 0% | 100% |
| STRAY_SEMICOLON | 1 | 100% | 100% | 0% | 100% |
| UNINIT_VAR | 1 | 100% | 100% | 100% | 100% |

## Đọc kết quả

- Rule-based và Hybrid xác định lỗi giống nhau (cùng tầng luật); khác nhau ở chất lượng giải thích, cần chấm thêm theo rubric (LLM-as-judge + người chấm).
- "Nghi lộ lời giải" là kiểm tra tự động thô (từ 3 dòng trông như code trong lời giải thích); cần người đọc lại các trường hợp bị đánh dấu.
- Rule-based và Hybrid dùng luật khử nhiễu khai phá từ chính tập dữ liệu này, nên số đo trên đây lạc quan (đánh giá trên dữ liệu đã học). Số đo trên bài chưa thấy: xem phần leave-one-problem-out trong `docs/mining_report.md`.
- "Dòng đúng" so với dòng bị cài lỗi; công cụ thường báo dòng lỗi biểu hiện (ví dụ bỏ `= 0` ở dòng khai báo nhưng gcc báo ở dòng cộng dồn), nên chỉ số này thấp hơn thực tế.
- Lỗi do máy cài vào lời giải mẫu, chưa phải bài làm thật của sinh viên.
