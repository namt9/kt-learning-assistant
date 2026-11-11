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
| `backend/app/kg/` | Kết nối và truy vấn Neo4j | A |
| `backend/app/student/` | Hồ sơ năng lực, phong cách học | E |
| `backend/app/schemas.py` | **Hợp đồng dữ liệu dùng chung** giữa các module (sửa phải qua PR, cả nhóm review) | Cả nhóm |
| `knowledge/` | Ontology (`.owl`), concept map, danh mục Bug Pattern | A |
| `data/problems/` | Ngân hàng bài tập + test case | C |
| `data/raw/` | Dataset log tải về (không commit, xem `data/README.md`) | C |
| `mining/` | Khai phá luật chẩn đoán | C |
| `evaluation/` | Benchmark và script so sánh LLM thuần / Rule-based / Hybrid | C |
| `sandbox/` | Docker image chạy code sinh viên | B |
| `frontend/` | Giao diện chat, KG viewer, hồ sơ năng lực | E |
| `docs/` | Đề bài, kế hoạch, kiến trúc, báo cáo | A |

## Chạy thử

Yêu cầu: Python 3.10+, Docker.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env            # rồi điền giá trị thật, KHÔNG commit .env
docker compose up -d neo4j       # Neo4j: http://localhost:7474
docker build -t kt-sandbox sandbox/
uvicorn backend.app.main:app --reload   # API: http://localhost:8000/docs
pytest
```

## Làm việc nhóm

Đọc [CONTRIBUTING.md](CONTRIBUTING.md) trước khi code.
