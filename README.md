# Trợ lý học tập thông minh: Multi-Agent + Knowledge Graph

Đồ án môn **Chuyên đề Công nghệ tri thức 2026**, Project 1 (đề bài: [`docs/De tai mon Cong nghe tri thuc 2026.pdf`](docs/)).
Kế hoạch 4 tuần và phân công: [`docs/Ke_hoach_Project1_4_tuan.xlsx`](docs/Ke_hoach_Project1_4_tuan.xlsx).

Hệ thống gồm hai phiên bản:

- **v0 (hệ nền, xây mới):** nộp code C/C++ → biên dịch, chạy test trong sandbox → báo lỗi bằng luật (gcc, cppcheck, ASan, luật tự viết) → lưu log. Bản này cũng là nhánh *Rule-based* khi so sánh.
- **v1 (mở rộng):** Ontology/Knowledge Graph, Multi-Agent (chấm điểm, chẩn đoán, lộ trình), RAG + LLM, Hybrid Reasoning, luật khai phá từ log, hồ sơ năng lực và phong cách học.

## Cấu trúc thư mục

| Thư mục | Nội dung | Phụ trách |
|---|---|---|
| `backend/app/judge/` | Sandbox, biên dịch, chạy test, chấm điểm | B |
| `backend/app/rules/` | Rule engine: ánh xạ cảnh báo công cụ sang Bug Pattern, luật tự viết | B, D |
| `backend/app/agents/` | Orchestrator, Grading / Diagnosis / Learning-Path Agent | D |
| `backend/app/rag/` | Pipeline RAG | D |
| `backend/app/kg/` | Kiểm tra tri thức, nạp và truy vấn Neo4j ([lược đồ](docs/kg_schema.md)) | A |
| `backend/app/student/` | Hồ sơ năng lực, phong cách học | E |
| `backend/app/schemas.py` | **Hợp đồng dữ liệu dùng chung** giữa các module (sửa phải qua PR, cả nhóm review) | Cả nhóm |
| `knowledge/` | Concept map, Bug Pattern, hành động sư phạm (YAML), ontology (`.owl`) | A |
| `data/problems/` | Ngân hàng bài tập + test case | C |
| `data/raw/` | Dataset log tải về (không commit, xem `data/README.md`) | C |
| `mining/` | Khai phá luật chẩn đoán | C |
| `evaluation/` | Benchmark và script so sánh LLM thuần / Rule-based / Hybrid | C |
| `sandbox/` | Docker image chạy code sinh viên | B |
| `frontend/` | `v0/index.html`: giao diện nộp bài v0; sau mở rộng thành chat, KG viewer, hồ sơ năng lực | E |
| `docs/` | Đề bài, kế hoạch, kiến trúc, báo cáo | A |

## Hệ nền v0 (đã có)

Luồng xử lý một lần nộp bài (`backend/app/judge/judge.py`):

1. Biên dịch bằng `gcc -std=c11` / `g++ -std=c++17` với `-Wall -Wextra`. Cảnh báo và lỗi được ánh xạ sang mã Bug Pattern.
2. Phân tích tĩnh: `cppcheck` (nếu có) cộng với 10 luật tự viết (`backend/app/rules/custom.py`): thiếu `&` trong scanf, `=` trong điều kiện, `;` thừa sau if/for/while, lệch biên vòng lặp, chia nguyên gán cho số thực, malloc không free, chia cho hằng 0, điều kiện luôn đúng/sai (số không dấu `>= 0`, so biến với chính nó), `while (1)` không có lối thoát, trả địa chỉ biến cục bộ.
3. Chạy test trong sandbox, trả về AC / WA / CE / RE / TLE / MLE và điểm theo tỉ lệ test đạt.
4. Biên dịch lại với AddressSanitizer + UBSan và chạy lại tối đa 3 test, ưu tiên test sai: phát hiện tràn mảng, rò rỉ bộ nhớ, dùng con trỏ đã free, NULL, tràn số...
5. Gộp và khử trùng lặp lỗi, gắn câu gợi ý cố định từ `knowledge/bug_patterns.yaml`, lưu log vào SQLite (bảng `submissions` và `findings`).

API (xem đầy đủ tại `/docs`): `GET /problems`, `GET /problems/{id}`, `POST /submit`,
`GET /submissions/{id}`, `GET /students/{id}/submissions`. Giao diện v0 nằm ở `/v0`, v1 ở `/`.

## Chạy bằng Docker Compose (dùng khi demo)

Chỉ cần Docker. Chạy từ thư mục gốc repo:

```bash
cp .env.example .env            # điền khoá LLM (không có khoá thì chẩn đoán lùi về luật + KG)
docker compose up -d --build    # build kt-sandbox + backend, chạy Neo4j, nạp KG
```

- v1 (trợ lý): http://localhost:8000 · v0: http://localhost:8000/v0 · KG: http://localhost:8000/kg-viewer · API: http://localhost:8000/docs
- Backend gọi Docker của máy chủ qua `/var/run/docker.sock` để chạy từng lần nộp trong container `kt-sandbox` (tắt mạng, giới hạn RAM/CPU/PID). Thư mục `.sandbox_work/` được mount cùng đường dẫn vào container, nên phải chạy lệnh từ thư mục repo (Docker Desktop: repo phải nằm dưới `/home`).
- Log nộp bài nằm trong volume `app_data`, tách khỏi `app.db` khi chạy trực tiếp.
- LLM local dự phòng: `docker compose --profile ollama up -d` rồi đặt `LLM_PROVIDERS=claude,ollama`.

## Chạy trực tiếp (phát triển)

Yêu cầu: Python 3.10+, gcc/g++, Docker (cho chế độ an toàn).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env            # rồi điền giá trị thật, KHÔNG commit .env
```

**Chế độ sandbox** (`SANDBOX_MODE` trong `.env`):

| Chế độ | Dùng khi | Cách chạy |
|---|---|---|
| `docker` | Demo, chấm code của người khác | `docker build -t kt-sandbox sandbox/` rồi `uvicorn backend.app.main:app --reload` |
| `local` | Tự phát triển, chạy test | `SANDBOX_MODE=local uvicorn backend.app.main:app --reload` |

`local` chạy code thẳng trên máy, chỉ giới hạn bằng rlimit nên **không an toàn**: chỉ dùng với code của chính mình.
Ở chế độ `local`, nếu máy không có `cppcheck` thì bước đó được bỏ qua và ghi vào `tools_unavailable` của kết quả.

Mở http://localhost:8000 để dùng giao diện, http://localhost:8000/docs để xem API.

```bash
pytest                           # test LocalRunner (cần gcc) + test Docker nếu đã build kt-sandbox
docker compose up -d neo4j       # Neo4j cho phần v1: http://localhost:7474
python -m backend.app.kg.load    # nạp Knowledge Graph (xem docs/kg_schema.md)
```

## Làm việc nhóm

Đọc [CONTRIBUTING.md](CONTRIBUTING.md) trước khi code.
