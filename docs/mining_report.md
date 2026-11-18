# Báo cáo khai phá luật chẩn đoán

> Sinh tự động bởi `python -m backend.app.mining.mine`. Không sửa tay.

## Dữ liệu

- 136 bài nộp giả lập từ 3 bài tập (cài lỗi có chủ đích vào lời giải mẫu, `backend/app/mining/mutate.py`), chấm bằng hệ v0. 101 bài mang 2 lỗi.
- Tham số: min_support=0.03, min_confidence=0.7, độ dài tập mục tối đa=4.
- Verdict: RE 61, WA 41, TLE 22, AC 7, CE 5

## Tầng luật v0 so với nhãn đúng

| Lỗi đã cài | Số bài | Recall | Precision | Verdict thường gặp |
|---|---|---|---|---|
| ARRAY_OOB | 5 | 100% | 23% | AC 2, TLE 2, RE 1 |
| ASSIGN_IN_COND | 7 | 100% | 100% | RE 7 |
| DANGLING_PTR | 10 | 80% | 62% | RE 4, WA 3, TLE 2, AC 1 |
| DOUBLE_FREE | 8 | 50% | 100% | RE 6, TLE 1, AC 1 |
| FORMAT_MISMATCH | 17 | 94% | 70% | WA 11, RE 4, TLE 2 |
| INFINITE_LOOP | 29 | 76% | 100% | TLE 22, RE 7 |
| INT_DIVISION | 9 | 100% | 100% | WA 6, RE 2, TLE 1 |
| INT_OVERFLOW | 8 | 62% | 100% | WA 5, RE 2, TLE 1 |
| MEM_LEAK | 9 | 78% | 50% | AC 4, RE 3, TLE 1, WA 1 |
| MISSING_BRACES | 8 | 100% | 33% | WA 5, RE 2, TLE 1 |
| NULL_DEREF | 6 | 100% | 15% | RE 6 |
| OFF_BY_ONE | 37 | 22% | 100% | WA 16, RE 15, TLE 3, AC 3 |
| SCANF_MISSING_AMP | 46 | 100% | 100% | RE 46 |
| STRAY_SEMICOLON | 16 | 100% | 100% | WA 10, RE 4, TLE 2 |
| SYNTAX_ERROR | 2 | 100% | 100% | CE 2 |
| UNDECLARED_ID | 3 | 100% | 100% | CE 3 |
| UNINIT_VAR | 17 | 100% | 35% | WA 11, RE 4, TLE 2 |

Recall thấp: công cụ bỏ sót hoặc gọi sai tên lỗi. Precision thấp: công cụ báo cả các hệ quả của lỗi gốc. Hai loại luật khai phá dưới đây nhắm vào hai vấn đề này.

## Luật khai phá (73 luật)

### Luật bổ sung: đoán lỗi thật công cụ bỏ sót / gọi sai tên (44 luật, top 15)

| # | Luật | Support | Confidence | Lift |
|---|---|---|---|---|
| MR001 | `{feat=free, found=MEM_LEAK} → lỗi thật ASSIGN_IN_COND` | 0.051 | 1.00 | 19.4 |
| MR002 | `{feat=malloc, found=UNCLASSIFIED} → lỗi thật ASSIGN_IN_COND` | 0.051 | 1.00 | 19.4 |
| MR003 | `{found=CONST_CONDITION, found=UNCLASSIFIED} → lỗi thật ASSIGN_IN_COND` | 0.051 | 1.00 | 19.4 |
| MR005 | `{feat=free, found=UNCLASSIFIED} → lỗi thật ASSIGN_IN_COND` | 0.051 | 1.00 | 19.4 |
| MR008 | `{feat=array_index, found=UNCLASSIFIED} → lỗi thật ASSIGN_IN_COND` | 0.051 | 1.00 | 19.4 |
| MR009 | `{found=MEM_LEAK, found=UNCLASSIFIED} → lỗi thật ASSIGN_IN_COND` | 0.051 | 1.00 | 19.4 |
| MR010 | `{found=CONST_CONDITION, found=MEM_LEAK} → lỗi thật ASSIGN_IN_COND` | 0.051 | 1.00 | 19.4 |
| MR011 | `{found=CONST_CONDITION, found=NULL_DEREF} → lỗi thật ASSIGN_IN_COND` | 0.044 | 1.00 | 19.4 |
| MR012 | `{found=MEM_LEAK, found=NULL_DEREF} → lỗi thật ASSIGN_IN_COND` | 0.044 | 1.00 | 19.4 |
| MR014 | `{feat=malloc, found=NULL_DEREF} → lỗi thật ASSIGN_IN_COND` | 0.044 | 1.00 | 19.4 |
| MR015 | `{feat=array_index, feat=cast, found=NULL_DEREF} → lỗi thật ASSIGN_IN_COND` | 0.044 | 1.00 | 19.4 |
| MR016 | `{feat=cast, feat=free, found=NULL_DEREF} → lỗi thật ASSIGN_IN_COND` | 0.044 | 1.00 | 19.4 |
| MR017 | `{feat=malloc_no_free} → lỗi thật MEM_LEAK` | 0.051 | 1.00 | 15.1 |
| MR019 | `{feat=long_long, found=MISSING_BRACES} → lỗi thật STRAY_SEMICOLON` | 0.051 | 1.00 | 8.5 |
| MR021 | `{verdict=TLE} → lỗi thật INFINITE_LOOP` | 0.162 | 1.00 | 4.7 |

### Luật khử nhiễu: cảnh báo chỉ là hệ quả của lỗi gốc khác (29 luật, top 15)

| # | Luật | Support | Confidence | Lift |
|---|---|---|---|---|
| MR004 | `{found=ASSIGN_IN_COND, found=MEM_LEAK} → bỏ MEM_LEAK` | 0.051 | 1.00 | 19.4 |
| MR006 | `{found=MEM_LEAK, found=UNCLASSIFIED} → bỏ MEM_LEAK` | 0.051 | 1.00 | 19.4 |
| MR007 | `{found=CONST_CONDITION, found=MEM_LEAK} → bỏ MEM_LEAK` | 0.051 | 1.00 | 19.4 |
| MR013 | `{found=MEM_LEAK, found=NULL_DEREF} → bỏ MEM_LEAK` | 0.044 | 1.00 | 19.4 |
| MR018 | `{found=MISSING_BRACES, found=STRAY_SEMICOLON} → bỏ MISSING_BRACES` | 0.118 | 1.00 | 8.5 |
| MR020 | `{found=ARRAY_OOB, found=UNINIT_VAR} → bỏ ARRAY_OOB` | 0.059 | 1.00 | 8.0 |
| MR022 | `{found=ARRAY_OOB, found=UNINIT_VAR} → bỏ UNINIT_VAR` | 0.059 | 1.00 | 4.2 |
| MR023 | `{found=FORMAT_MISMATCH, found=UNINIT_VAR, verdict=RE} → bỏ UNINIT_VAR` | 0.044 | 1.00 | 4.2 |
| MR024 | `{found=FORMAT_MISMATCH, found=SCANF_MISSING_AMP, found=UNINIT_VAR} → bỏ UNINIT_VAR` | 0.044 | 1.00 | 4.2 |
| MR025 | `{found=MISSING_BRACES, found=SCANF_MISSING_AMP, found=UNINIT_VAR} → bỏ UNINIT_VAR` | 0.044 | 1.00 | 4.2 |
| MR026 | `{found=MISSING_BRACES, found=NULL_DEREF, found=UNINIT_VAR} → bỏ UNINIT_VAR` | 0.044 | 1.00 | 4.2 |
| MR027 | `{found=MISSING_BRACES, found=UNINIT_VAR, verdict=RE} → bỏ UNINIT_VAR` | 0.044 | 1.00 | 4.2 |
| MR028 | `{found=FORMAT_MISMATCH, found=NULL_DEREF, found=UNINIT_VAR} → bỏ UNINIT_VAR` | 0.037 | 1.00 | 4.2 |
| MR029 | `{found=NULL_DEREF, found=UNINIT_VAR} → bỏ NULL_DEREF` | 0.213 | 1.00 | 3.9 |
| MR030 | `{found=NULL_DEREF, found=UNCLASSIFIED} → bỏ NULL_DEREF` | 0.051 | 1.00 | 3.9 |


## Đánh giá leave-one-problem-out

Khai phá luật trên các bài còn lại, kiểm tra trên bài để riêng (bài chưa thấy khi khai phá). Áp dụng luật có confidence ≥ 0.8.

Mỗi ô: precision / recall / F1 khi đoán tập lỗi thật của từng bài nộp, chỉ tính trên các mã lỗi có nhãn đúng (mã bộ mutation cài được).

| Bài kiểm tra | Số bài nộp | Số luật | Chỉ tầng luật v0 | + luật bổ sung | + luật khử nhiễu | + cả hai |
|---|---|---|---|---|---|---|
| P001 | 37 | 69 | 0.54 / 0.78 / 0.64 | 0.54 / 0.78 / 0.64 | 0.87 / 0.75 / 0.81 | 0.87 / 0.75 / 0.81 |
| P002 | 54 | 21 | 0.65 / 0.76 / 0.70 | 0.57 / 0.76 / 0.65 | 0.71 / 0.69 / 0.70 | 0.61 / 0.69 / 0.65 |
| P003 | 45 | 64 | 0.64 / 0.86 / 0.74 | 0.48 / 0.94 / 0.63 | 1.00 / 0.73 / 0.85 | 0.60 / 0.81 / 0.69 |

F1 trung bình: baseline 0.69, add 0.64, suppress 0.78, both 0.71.

## Kết luận

- Cấu hình tốt nhất trên bài chưa thấy: **thêm luật khử nhiễu** (F1 trung bình 0.69 → 0.78).
- Luật khử nhiễu tổng quát được vì mô tả quan hệ giữa các cảnh báo (lỗi gốc kéo theo cảnh báo hệ quả), không phụ thuộc bài tập cụ thể.
- Luật bổ sung làm giảm F1 (0.69 → 0.64): với ít bài tập, chúng dễ học thuộc đặc điểm của từng bài. Chỉ nên đưa vào rule engine khi có thêm bài tập và log thật.

## Hạn chế

- Mới có 3 bài tập và lỗi do máy cài, chưa phải log sinh viên thật: luật phản ánh cách hệ v0 phản ứng với từng loại lỗi hơn là thói quen của sinh viên.
- Thêm bài tập (mục tiêu 10–15) và log thật thì chạy lại hai lệnh `generate`, `mine`.
