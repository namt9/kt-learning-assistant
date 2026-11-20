# Báo cáo khai phá luật chẩn đoán

> Sinh tự động bởi `python -m backend.app.mining.mine`. Không sửa tay.

## Dữ liệu

- 270 bài nộp giả lập từ 10 bài tập (cài lỗi có chủ đích vào lời giải mẫu, `backend/app/mining/mutate.py`), chấm bằng hệ v0. 191 bài mang 2 lỗi.
- Tham số: min_support=0.03, min_confidence=0.7, độ dài tập mục tối đa=4.
- Verdict: RE 135, TLE 59, WA 53, AC 12, CE 11

## Tầng luật v0 so với nhãn đúng

| Lỗi đã cài | Số bài | Recall | Precision | Verdict thường gặp |
|---|---|---|---|---|
| ARRAY_OOB | 5 | 100% | 12% | AC 2, TLE 2, RE 1 |
| ASSIGN_IN_COND | 13 | 100% | 100% | RE 13 |
| DANGLING_PTR | 15 | 80% | 63% | RE 10, WA 3, TLE 2 |
| DOUBLE_FREE | 15 | 40% | 100% | RE 11, TLE 2, AC 2 |
| FORMAT_MISMATCH | 26 | 96% | 78% | WA 15, RE 7, TLE 4 |
| INFINITE_LOOP | 90 | 66% | 100% | TLE 59, RE 31 |
| INT_DIVISION | 9 | 100% | 100% | WA 6, RE 2, TLE 1 |
| INT_OVERFLOW | 8 | 62% | 50% | WA 5, RE 2, TLE 1 |
| MEM_LEAK | 13 | 69% | 45% | AC 5, RE 5, TLE 2, WA 1 |
| MISSING_BRACES | 8 | 100% | 27% | WA 5, RE 2, TLE 1 |
| NULL_DEREF | 12 | 100% | 12% | RE 12 |
| OFF_BY_ONE | 83 | 45% | 100% | RE 32, WA 24, TLE 20, AC 7 |
| SCANF_MISSING_AMP | 104 | 100% | 100% | RE 104 |
| STRAY_SEMICOLON | 22 | 100% | 100% | WA 12, RE 7, TLE 3 |
| SYNTAX_ERROR | 3 | 100% | 100% | CE 3 |
| UNDECLARED_ID | 8 | 100% | 100% | CE 8 |
| UNINIT_VAR | 27 | 100% | 28% | WA 14, RE 7, TLE 6 |

Recall thấp: công cụ bỏ sót hoặc gọi sai tên lỗi. Precision thấp: công cụ báo cả các hệ quả của lỗi gốc. Hai loại luật khai phá dưới đây nhắm vào hai vấn đề này.

## Luật khai phá (68 luật)

### Luật bổ sung: đoán lỗi thật công cụ bỏ sót / gọi sai tên (39 luật, top 15)

| # | Luật | Support | Confidence | Lift |
|---|---|---|---|---|
| MR001 | `{found=CONST_CONDITION, found=UNCLASSIFIED} → lỗi thật ASSIGN_IN_COND` | 0.044 | 1.00 | 20.8 |
| MR002 | `{found=CONST_CONDITION, found=MEM_LEAK} → lỗi thật ASSIGN_IN_COND` | 0.044 | 1.00 | 20.8 |
| MR003 | `{found=CONST_CONDITION, found=NULL_DEREF} → lỗi thật ASSIGN_IN_COND` | 0.044 | 1.00 | 20.8 |
| MR004 | `{found=MEM_LEAK, found=UNCLASSIFIED} → lỗi thật ASSIGN_IN_COND` | 0.044 | 1.00 | 20.8 |
| MR005 | `{feat=array_index, found=UNCLASSIFIED} → lỗi thật ASSIGN_IN_COND` | 0.044 | 1.00 | 20.8 |
| MR006 | `{feat=malloc, found=UNCLASSIFIED} → lỗi thật ASSIGN_IN_COND` | 0.044 | 1.00 | 20.8 |
| MR007 | `{feat=free, found=MEM_LEAK} → lỗi thật ASSIGN_IN_COND` | 0.041 | 1.00 | 20.8 |
| MR008 | `{feat=free, found=UNCLASSIFIED} → lỗi thật ASSIGN_IN_COND` | 0.041 | 1.00 | 20.8 |
| MR009 | `{found=MEM_LEAK, found=NULL_DEREF} → lỗi thật ASSIGN_IN_COND` | 0.041 | 1.00 | 20.8 |
| MR010 | `{feat=malloc, found=NULL_DEREF} → lỗi thật ASSIGN_IN_COND` | 0.041 | 1.00 | 20.8 |
| MR011 | `{feat=malloc_no_free} → lỗi thật MEM_LEAK` | 0.033 | 1.00 | 20.8 |
| MR021 | `{verdict=TLE} → lỗi thật INFINITE_LOOP` | 0.219 | 1.00 | 3.0 |
| MR022 | `{found=UNINIT_VAR, verdict=RE} → lỗi thật SCANF_MISSING_AMP` | 0.285 | 1.00 | 2.6 |
| MR023 | `{found=NULL_DEREF, found=UNINIT_VAR} → lỗi thật SCANF_MISSING_AMP` | 0.211 | 1.00 | 2.6 |
| MR024 | `{found=ARRAY_OOB, verdict=RE} → lỗi thật SCANF_MISSING_AMP` | 0.115 | 1.00 | 2.6 |

### Luật khử nhiễu: cảnh báo chỉ là hệ quả của lỗi gốc khác (29 luật, top 15)

| # | Luật | Support | Confidence | Lift |
|---|---|---|---|---|
| MR012 | `{found=MISSING_BRACES, found=STRAY_SEMICOLON} → bỏ MISSING_BRACES` | 0.081 | 1.00 | 12.3 |
| MR013 | `{found=ARRAY_OOB, found=UNINIT_VAR} → bỏ ARRAY_OOB` | 0.085 | 1.00 | 7.7 |
| MR014 | `{found=ARRAY_OOB, found=UNINIT_VAR} → bỏ UNINIT_VAR` | 0.085 | 1.00 | 3.9 |
| MR015 | `{found=MISSING_BRACES, found=UNINIT_VAR, verdict=RE} → bỏ UNINIT_VAR` | 0.033 | 1.00 | 3.9 |
| MR016 | `{found=MISSING_BRACES, found=SCANF_MISSING_AMP, found=UNINIT_VAR} → bỏ UNINIT_VAR` | 0.033 | 1.00 | 3.9 |
| MR017 | `{found=NULL_DEREF, found=UNINIT_VAR} → bỏ NULL_DEREF` | 0.211 | 1.00 | 3.2 |
| MR018 | `{found=NULL_DEREF, found=UNCLASSIFIED} → bỏ NULL_DEREF` | 0.044 | 1.00 | 3.2 |
| MR019 | `{found=MEM_LEAK, found=NULL_DEREF} → bỏ NULL_DEREF` | 0.041 | 1.00 | 3.2 |
| MR020 | `{found=NULL_DEREF, found=OFF_BY_ONE, found=SCANF_MISSING_AMP} → bỏ NULL_DEREF` | 0.033 | 1.00 | 3.2 |
| MR034 | `{found=NULL_DEREF, found=SCANF_MISSING_AMP} → bỏ NULL_DEREF` | 0.278 | 0.99 | 3.1 |
| MR035 | `{found=ARRAY_OOB, verdict=RE} → bỏ ARRAY_OOB` | 0.111 | 0.97 | 7.5 |
| MR036 | `{found=ARRAY_OOB, found=SCANF_MISSING_AMP} → bỏ ARRAY_OOB` | 0.111 | 0.97 | 7.5 |
| MR038 | `{found=CONST_CONDITION, found=MEM_LEAK} → bỏ MEM_LEAK` | 0.041 | 0.92 | 22.5 |
| MR039 | `{found=MEM_LEAK, found=UNCLASSIFIED} → bỏ MEM_LEAK` | 0.041 | 0.92 | 22.5 |
| MR040 | `{found=ASSIGN_IN_COND, found=MEM_LEAK} → bỏ MEM_LEAK` | 0.041 | 0.92 | 22.5 |


## Đánh giá leave-one-problem-out

Khai phá luật trên các bài còn lại, kiểm tra trên bài để riêng (bài chưa thấy khi khai phá). Áp dụng luật có confidence ≥ 0.8.

Mỗi ô: precision / recall / F1 khi đoán tập lỗi thật của từng bài nộp, chỉ tính trên các mã lỗi có nhãn đúng (mã bộ mutation cài được).

| Bài kiểm tra | Số bài nộp | Số luật | Chỉ tầng luật v0 | + luật bổ sung | + luật khử nhiễu | + cả hai |
|---|---|---|---|---|---|---|
| P001 | 37 | 60 | 0.55 / 0.78 / 0.65 | 0.52 / 0.78 / 0.62 | 0.87 / 0.75 / 0.81 | 0.79 / 0.75 / 0.77 |
| P002 | 53 | 54 | 0.64 / 0.76 / 0.70 | 0.54 / 0.76 / 0.63 | 0.83 / 0.64 / 0.72 | 0.64 / 0.64 / 0.64 |
| P003 | 45 | 56 | 0.64 / 0.86 / 0.74 | 0.56 / 0.86 / 0.68 | 1.00 / 0.73 / 0.85 | 0.78 / 0.73 / 0.76 |
| P004 | 19 | 73 | 0.59 / 0.71 / 0.65 | 0.59 / 0.71 / 0.65 | 1.00 / 0.71 / 0.83 | 1.00 / 0.71 / 0.83 |
| P005 | 1 | 67 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 |
| P006 | 45 | 77 | 0.63 / 0.87 / 0.73 | 0.59 / 0.87 / 0.70 | 0.93 / 0.83 / 0.88 | 0.83 / 0.83 / 0.83 |
| P007 | 26 | 65 | 0.65 / 0.77 / 0.71 | 0.65 / 0.80 / 0.71 | 1.00 / 0.77 / 0.87 | 0.97 / 0.80 / 0.88 |
| P008 | 21 | 45 | 0.63 / 0.67 / 0.65 | 0.42 / 0.67 / 0.52 | 0.75 / 0.50 / 0.60 | 0.42 / 0.50 / 0.46 |
| P009 | 19 | 61 | 0.40 / 0.71 / 0.51 | 0.40 / 0.71 / 0.51 | 1.00 / 0.71 / 0.83 | 1.00 / 0.71 / 0.83 |
| P010 | 4 | 70 | 0.56 / 1.00 / 0.71 | 0.56 / 1.00 / 0.71 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 |

F1 trung bình: baseline 0.70, add 0.67, suppress 0.84, both 0.80.

## Kết luận

- Cấu hình tốt nhất trên bài chưa thấy: **thêm luật khử nhiễu** (F1 trung bình 0.70 → 0.84).
- Luật khử nhiễu tổng quát được vì mô tả quan hệ giữa các cảnh báo (lỗi gốc kéo theo cảnh báo hệ quả), không phụ thuộc bài tập cụ thể.
- Luật bổ sung làm giảm F1 (0.70 → 0.67): với ít bài tập, chúng dễ học thuộc đặc điểm của từng bài. Chỉ nên đưa vào rule engine khi có thêm bài tập và log thật.

## Hạn chế

- Mới có 10 bài tập và lỗi do máy cài, chưa phải log sinh viên thật: luật phản ánh cách hệ v0 phản ứng với từng loại lỗi hơn là thói quen của sinh viên.
- Thêm bài tập (mục tiêu 10–15) và log thật thì chạy lại hai lệnh `generate`, `mine`.
