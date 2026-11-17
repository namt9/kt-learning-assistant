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
| v0 (hệ nền, xây mới, **đã xong**) | judge (sandbox Docker/local), rule engine (gcc + cppcheck + ASan/UBSan + 6 luật tự viết, 21 Bug Pattern), gợi ý template, log SQLite, UI nộp bài |
| v1 (mở rộng) | Ontology/KG, Multi-Agent, RAG + LLM, Hybrid Reasoning, luật khai phá, hồ sơ năng lực, phong cách học |
