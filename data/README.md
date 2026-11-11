# Data (C)

## `problems/`: ngân hàng bài tập (có commit)

Mỗi bài một thư mục `P<số>_<tên>/`:

```
problem.yaml     # id, tiêu đề, giới hạn thời gian/bộ nhớ, concept liên quan
statement.md     # đề bài
solution.c       # lời giải mẫu
tests/1.in, 1.out, ...
```

`P001`–`P003` là bài mẫu để làm theo. Test tự động kiểm tra mọi `solution.c` phải đạt AC và không có lỗi nghiêm trọng.

Log nộp bài của hệ v0 nằm trong SQLite (`DB_PATH`): bảng `submissions` (mã nguồn, verdict, điểm) và `findings` (mã Bug Pattern, nguồn phát hiện, dòng). Đây là đầu vào cho phần khai phá luật.

## `raw/`: dataset log (KHÔNG commit)

Tải về máy theo hướng dẫn dưới đây. Thư mục này đã nằm trong `.gitignore`.

| Dataset | Nguồn | Ghi chú |
|---|---|---|
| ITSP / Prutor | (điền link) | bài nộp C thật của sinh viên |
| DeepFix | (điền link) | chương trình C có lỗi biên dịch |
| Project CodeNet | (điền link) | lọc phần C/C++ |

Kiểm tra license trước khi dùng và ghi lại vào bảng trên.
