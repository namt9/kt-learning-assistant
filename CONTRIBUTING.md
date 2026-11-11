# Quy ước làm việc nhóm

## Thành viên

| Mã | Họ tên | GitHub | Vai trò |
|---|---|---|---|
| A | | | Trưởng nhóm / Knowledge Engineer |
| B | | | Backend & Rule-based |
| C | | | Data & Mining |
| D | | | LLM/RAG & Multi-Agent |
| E | | | Frontend & Student Model |

## Quy trình Git

1. **Không push thẳng lên `main`.** `main` luôn phải chạy được.
2. Mỗi việc trong file kế hoạch là một **issue**. Tạo nhánh từ `main` theo issue:
   ```bash
   git switch main && git pull
   git switch -c feat/12-judge-sandbox      # <loại>/<số issue>-<mô tả ngắn>
   ```
   Loại nhánh: `feat`, `fix`, `docs`, `data`, `exp` (thử nghiệm).
3. Commit nhỏ, thông điệp rõ ràng:
   ```
   feat(judge): chạy test case trong sandbox Docker
   fix(rules): bỏ cảnh báo trùng của cppcheck
   docs: thêm sơ đồ kiến trúc
   ```
4. Push và mở **Pull Request** vào `main`, điền template, gắn `Closes #12`.
5. Cần **ít nhất 1 người duyệt** và CI xanh mới được merge. Ưu tiên *Squash and merge*.
6. Trước khi mở PR: `git pull --rebase origin main`, chạy `ruff check .` và `pytest`.

## Quy tắc chung

- Thay đổi `backend/app/schemas.py` (hợp đồng dữ liệu giữa các module) phải báo cả nhóm và cần 2 người duyệt.
- **Không commit:** file `.env`, API key, mật khẩu, dataset lớn (`data/raw/`), file mô hình, thư mục `.venv`.
- Code Python: format bằng `ruff format`, kiểm tra bằng `ruff check`.
- Mỗi module có test tối thiểu trong `backend/tests/`.
- Làm module của người khác chưa xong? Dùng **mock** theo đúng `schemas.py`, đừng chờ.
- Họp ngắn 15 phút mỗi 2–3 ngày; cập nhật trạng thái trong file kế hoạch hoặc trên issue.
