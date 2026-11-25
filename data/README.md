# Data (C)

## `problems/`: ngân hàng bài tập (có commit)

Mỗi bài một thư mục `P<số>_<tên>/`:

```
problem.yaml     # id, tiêu đề, giới hạn thời gian/bộ nhớ, concept liên quan
statement.md     # đề bài
solution.c       # lời giải mẫu
tests/1.in, 1.out, ...
```

`P001`–`P010`: 10 bài (mảng, chuỗi, mảng 2 chiều, struct, ngăn xếp, con trỏ, đệ quy, cấp phát động). Test tự động kiểm tra mọi `solution.c` phải đạt AC và không có lỗi nghiêm trọng.

Log nộp bài của hệ v0 nằm trong SQLite (`DB_PATH`): bảng `submissions` (mã nguồn, verdict, điểm) và `findings` (mã Bug Pattern, nguồn phát hiện, dòng). Đây là đầu vào cho phần khai phá luật.

## `raw/`: dataset log (KHÔNG commit)

Tải về máy theo hướng dẫn dưới đây. Thư mục này đã nằm trong `.gitignore`.

| Dataset | Nguồn | Ghi chú |
|---|---|---|
| ITSP / Prutor | (điền link) | bài nộp C thật của sinh viên |
| DeepFix | (điền link) | chương trình C có lỗi biên dịch |
| Project CodeNet | (điền link) | lọc phần C/C++ |

Kiểm tra license trước khi dùng và ghi lại vào bảng trên.

## `mined/`: log có nhãn để khai phá luật (có commit)

Chưa có log sinh viên thật nên nhóm tự sinh: cài lỗi có chủ đích vào `solution.c` của từng bài
(`backend/app/mining/mutate.py`), rồi chấm bằng hệ v0. Mỗi dòng của `mutants.jsonl` là một bài
nộp kèm **nhãn đúng** (lỗi đã cài), verdict và các lỗi tầng luật phát hiện. File này dùng làm
benchmark có nhãn cho phần đánh giá ở tuần 4.

```bash
python -m backend.app.mining.generate --pairs 40 --jobs 6   # chấm lại (cần sandbox), vài phút
python -m backend.app.mining.mine                           # luật + báo cáo, vài giây
```

Kết quả: `knowledge/mined_rules.yaml` và `docs/mining_report.md`. Thêm bài tập mới vào `problems/`
thì chạy lại hai lệnh trên.
