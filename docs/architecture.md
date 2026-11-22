# Kiến trúc (bản nháp, chốt tuần 1)

```
[Web UI: Chat + KG Viewer + Hồ sơ năng lực]
              │
      [Orchestrator / Router Agent]
     ┌────────┼──────────────────┬──────────────────┐
[Grading Agent]   [Diagnosis Agent]        [Learning-Path Agent]
 judge + test      rule engine + KG + RAG   truy vấn KG:
                   → LLM giải thích         Bug → Remediated_By → Pedagogical_Action
              │
   [Neo4j KG + Ontology]   [Vector DB]   [Log DB: SQLite]
```

Hợp đồng dữ liệu giữa các khối: `backend/app/schemas.py`.

| Phiên bản | Thành phần |
|---|---|
| v0 (hệ nền, xây mới, **đã xong**) | judge (sandbox Docker/local), rule engine (gcc + cppcheck + ASan/UBSan + 6 luật tự viết lúc gắn tag v0, nay 10; 21 Bug Pattern), gợi ý template, log SQLite, UI nộp bài |
| v1 (mở rộng) | Ontology/KG, Multi-Agent, RAG + LLM, Hybrid Reasoning, luật khai phá, hồ sơ năng lực, phong cách học |

Ghi chú khi cài đặt (cập nhật 22/11): RAG tài liệu và Vector DB đã cắt ngày 20/11 vì thuyết trình dời lên 2/12; LLM được neo vào dữ kiện truy xuất từ KG thay cho tài liệu. Orchestrator viết bằng Python thuần thay cho LangGraph vì luồng cố định. Mô tả chi tiết: `docs/bao_cao/phuong_phap.md`.
