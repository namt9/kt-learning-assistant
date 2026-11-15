# Knowledge (A)

| File | Nội dung |
|---|---|
| `concepts.yaml` | Concept map C/C++: 5 cụm, 35 khái niệm, quan hệ tiên quyết |
| `bug_patterns.yaml` | 23 mẫu lỗi, khái niệm liên quan, gợi ý cố định của v0 |
| `pedagogical_actions.yaml` | 36 hành động sư phạm: sửa lỗi nào, dạy khái niệm nào, hợp phong cách học nào |
| `ontology/` | Ontology OWL thiết kế bằng Protégé (cho báo cáo) |

Lược đồ đồ thị và cách nạp vào Neo4j: [docs/kg_schema.md](../docs/kg_schema.md).

Sau khi sửa YAML, luôn chạy:

```bash
python -m backend.app.kg.load --check
```

Lệnh này báo **lỗi** (tham chiếu tới id không tồn tại, chu trình tiên quyết, mẫu lỗi chưa có cách
khắc phục) và **cảnh báo** (nội dung còn thiếu). Danh sách cảnh báo hiện tại là việc cần bổ sung:
- 9 khái niệm chưa có hành động dạy: `hang_so`, `so_hoc_con_tro`, `con_tro_va_mang`,
  `con_tro_hai_cap`, `mang_2_chieu`, `chuoi`, `struct`, `ngan_xep`, `hang_doi`
  (cần thêm bài tập và mẫu lỗi về chuỗi, struct, danh sách liên kết).
- 13 mẫu lỗi chưa có đủ hành động cho cả người học kiểu trực quan (`visual`) và kiểu lời giải thích (`verbal`).
