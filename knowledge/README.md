# Knowledge (A)

- `bug_patterns.yaml`: danh mục Bug Pattern dùng chung (có test kiểm tra tính hợp lệ).
- `ontology/`: ontology OWL thiết kế bằng Protégé (`.owl`).
- `concept_map/`: concept map C/C++ (Biến, Con trỏ, CTDL, Quản lý bộ nhớ).
- Script nạp KG vào Neo4j đặt ở `backend/app/kg/`.

Lược đồ chính: `[Student_Code] -(Exhibits)-> [Bug_Pattern] -(Remediated_By)-> [Pedagogical_Action]`,
cùng `Bug_Pattern -(Related_To)-> Concept` và `Concept -(Prerequisite_Of)-> Concept`.
