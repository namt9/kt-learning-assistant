# Báo cáo khai phá luật chẩn đoán

> Sinh tự động bởi `python -m backend.app.mining.mine`. Không sửa tay.

## Dữ liệu

- 135 bài nộp giả lập từ 3 bài tập (cài lỗi có chủ đích vào lời giải mẫu, `backend/app/mining/mutate.py`), chấm bằng hệ v0. 101 bài mang 2 lỗi.
- Tham số: min_support=0.03, min_confidence=0.7, độ dài tập mục tối đa=4.
- Verdict: RE 56, WA 43, TLE 24, AC 7, CE 5

## Tầng luật v0 so với nhãn đúng

| Lỗi đã cài | Số bài | Recall | Precision | Verdict thường gặp |
|---|---|---|---|---|
| ARRAY_OOB | 8 | 88% | 30% | AC 2, TLE 2, RE 2, WA 2 |
| ASSIGN_IN_COND | 8 | 100% | 100% | RE 8 |
| DANGLING_PTR | 12 | 75% | 60% | RE 5, WA 4, TLE 2, AC 1 |
| DOUBLE_FREE | 10 | 30% | 100% | RE 8, TLE 1, AC 1 |
| FORMAT_MISMATCH | 17 | 94% | 70% | WA 11, RE 4, TLE 2 |
| INFINITE_LOOP | 29 | 83% | 100% | TLE 24, RE 5 |
| INT_DIVISION | 9 | 100% | 100% | WA 6, RE 2, TLE 1 |
| INT_OVERFLOW | 8 | 62% | 100% | WA 5, RE 2, TLE 1 |
| MEM_LEAK | 7 | 86% | 43% | AC 4, TLE 1, WA 1, RE 1 |
| MISSING_BRACES | 8 | 100% | 33% | WA 5, RE 2, TLE 1 |
| OFF_BY_ONE | 38 | 21% | 100% | WA 17, RE 13, TLE 5, AC 3 |
| SCANF_MISSING_AMP | 44 | 100% | 100% | RE 44 |
| STRAY_SEMICOLON | 16 | 100% | 100% | WA 10, RE 4, TLE 2 |
| SYNTAX_ERROR | 2 | 100% | 100% | CE 2 |
| UNDECLARED_ID | 3 | 100% | 100% | CE 3 |
| UNINIT_VAR | 17 | 100% | 35% | WA 11, RE 4, TLE 2 |

Recall thấp: công cụ bỏ sót hoặc gọi sai tên lỗi. Precision thấp: công cụ báo cả các hệ quả của lỗi gốc. Hai loại luật khai phá dưới đây nhắm vào hai vấn đề này.

## Luật khai phá (63 luật)

### Luật bổ sung: đoán lỗi thật công cụ bỏ sót / gọi sai tên (43 luật, top 15)

| # | Luật | Support | Confidence | Lift |
|---|---|---|---|---|
| MR001 | `{feat=malloc_no_free} → lỗi thật MEM_LEAK` | 0.044 | 1.00 | 19.3 |
| MR003 | `{found=MEM_LEAK, found=UNCLASSIFIED} → lỗi thật ASSIGN_IN_COND` | 0.059 | 1.00 | 16.9 |
| MR004 | `{found=CONST_CONDITION, found=NULL_DEREF} → lỗi thật ASSIGN_IN_COND` | 0.059 | 1.00 | 16.9 |
| MR006 | `{feat=free, found=MEM_LEAK} → lỗi thật ASSIGN_IN_COND` | 0.059 | 1.00 | 16.9 |
| MR007 | `{found=MEM_LEAK, found=NULL_DEREF} → lỗi thật ASSIGN_IN_COND` | 0.059 | 1.00 | 16.9 |
| MR009 | `{feat=array_index, found=UNCLASSIFIED} → lỗi thật ASSIGN_IN_COND` | 0.059 | 1.00 | 16.9 |
| MR010 | `{found=CONST_CONDITION, found=MEM_LEAK} → lỗi thật ASSIGN_IN_COND` | 0.059 | 1.00 | 16.9 |
| MR011 | `{found=CONST_CONDITION, found=UNCLASSIFIED} → lỗi thật ASSIGN_IN_COND` | 0.059 | 1.00 | 16.9 |
| MR012 | `{feat=malloc, found=UNCLASSIFIED} → lỗi thật ASSIGN_IN_COND` | 0.059 | 1.00 | 16.9 |
| MR013 | `{feat=free, found=UNCLASSIFIED} → lỗi thật ASSIGN_IN_COND` | 0.059 | 1.00 | 16.9 |
| MR016 | `{feat=long_long, found=MISSING_BRACES} → lỗi thật STRAY_SEMICOLON` | 0.052 | 1.00 | 8.4 |
| MR019 | `{verdict=TLE} → lỗi thật INFINITE_LOOP` | 0.178 | 1.00 | 4.7 |
| MR026 | `{found=UNINIT_VAR, verdict=RE} → lỗi thật SCANF_MISSING_AMP` | 0.267 | 1.00 | 3.1 |
| MR027 | `{found=NULL_DEREF, found=UNINIT_VAR} → lỗi thật SCANF_MISSING_AMP` | 0.215 | 1.00 | 3.1 |
| MR028 | `{feat=division, verdict=RE} → lỗi thật SCANF_MISSING_AMP` | 0.119 | 1.00 | 3.1 |

### Luật khử nhiễu: cảnh báo chỉ là hệ quả của lỗi gốc khác (20 luật, top 15)

| # | Luật | Support | Confidence | Lift |
|---|---|---|---|---|
| MR002 | `{found=CONST_CONDITION, found=MEM_LEAK} → bỏ MEM_LEAK` | 0.059 | 1.00 | 16.9 |
| MR005 | `{found=ASSIGN_IN_COND, found=MEM_LEAK} → bỏ MEM_LEAK` | 0.059 | 1.00 | 16.9 |
| MR008 | `{found=MEM_LEAK, found=UNCLASSIFIED} → bỏ MEM_LEAK` | 0.059 | 1.00 | 16.9 |
| MR014 | `{found=MEM_LEAK, found=NULL_DEREF} → bỏ MEM_LEAK` | 0.059 | 1.00 | 16.9 |
| MR015 | `{found=MISSING_BRACES, found=STRAY_SEMICOLON} → bỏ MISSING_BRACES` | 0.119 | 1.00 | 8.4 |
| MR017 | `{found=ARRAY_OOB, found=UNINIT_VAR} → bỏ ARRAY_OOB` | 0.052 | 1.00 | 8.4 |
| MR018 | `{found=ARRAY_OOB, found=DANGLING_PTR, verdict=RE} → bỏ ARRAY_OOB` | 0.037 | 1.00 | 8.4 |
| MR020 | `{found=ARRAY_OOB, found=UNINIT_VAR} → bỏ UNINIT_VAR` | 0.052 | 1.00 | 4.2 |
| MR021 | `{found=MISSING_BRACES, found=SCANF_MISSING_AMP, found=UNINIT_VAR} → bỏ UNINIT_VAR` | 0.044 | 1.00 | 4.2 |
| MR022 | `{found=MISSING_BRACES, found=NULL_DEREF, found=UNINIT_VAR} → bỏ UNINIT_VAR` | 0.044 | 1.00 | 4.2 |
| MR023 | `{found=MISSING_BRACES, found=UNINIT_VAR, verdict=RE} → bỏ UNINIT_VAR` | 0.044 | 1.00 | 4.2 |
| MR024 | `{found=FORMAT_MISMATCH, found=SCANF_MISSING_AMP, found=UNINIT_VAR} → bỏ UNINIT_VAR` | 0.044 | 1.00 | 4.2 |
| MR025 | `{found=FORMAT_MISMATCH, found=UNINIT_VAR, verdict=RE} → bỏ UNINIT_VAR` | 0.044 | 1.00 | 4.2 |
| MR041 | `{found=ARRAY_OOB, verdict=RE} → bỏ ARRAY_OOB` | 0.104 | 0.93 | 7.9 |
| MR043 | `{found=ARRAY_OOB, found=SCANF_MISSING_AMP} → bỏ ARRAY_OOB` | 0.096 | 0.93 | 7.8 |


## Đánh giá leave-one-problem-out

Khai phá luật trên các bài còn lại, kiểm tra trên bài để riêng (bài chưa thấy khi khai phá). Áp dụng luật có confidence ≥ 0.8.

Mỗi ô: precision / recall / F1 khi đoán tập lỗi thật của từng bài nộp, chỉ tính trên các mã lỗi có nhãn đúng (mã bộ mutation cài được).

| Bài kiểm tra | Số bài nộp | Số luật | Chỉ tầng luật v0 | + luật bổ sung | + luật khử nhiễu | + cả hai |
|---|---|---|---|---|---|---|
| P001 | 37 | 58 | 0.63 / 0.78 / 0.70 | 0.63 / 0.78 / 0.70 | 0.87 / 0.75 / 0.81 | 0.87 / 0.75 / 0.81 |
| P002 | 53 | 20 | 0.66 / 0.72 / 0.69 | 0.59 / 0.72 / 0.65 | 0.71 / 0.72 / 0.71 | 0.63 / 0.72 / 0.67 |
| P003 | 45 | 55 | 0.76 / 0.86 / 0.80 | 0.56 / 0.86 / 0.68 | 1.00 / 0.73 / 0.85 | 0.65 / 0.73 / 0.69 |

F1 trung bình: baseline 0.73, add 0.68, suppress 0.79, both 0.72.

## Kết luận

- Cấu hình tốt nhất trên bài chưa thấy: **thêm luật khử nhiễu** (F1 trung bình 0.73 → 0.79).
- Luật khử nhiễu tổng quát được vì mô tả quan hệ giữa các cảnh báo (lỗi gốc kéo theo cảnh báo hệ quả), không phụ thuộc bài tập cụ thể.
- Luật bổ sung làm giảm F1 (0.73 → 0.68): với ít bài tập, chúng dễ học thuộc đặc điểm của từng bài. Chỉ nên đưa vào rule engine khi có thêm bài tập và log thật.

## Hạn chế

- Mới có 3 bài tập và lỗi do máy cài, chưa phải log sinh viên thật: luật phản ánh cách hệ v0 phản ứng với từng loại lỗi hơn là thói quen của sinh viên.
- Thêm bài tập (mục tiêu 10–15) và log thật thì chạy lại hai lệnh `generate`, `mine`.
