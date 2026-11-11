"""Rule engine v0: gộp Finding từ mọi nguồn, khử trùng lặp, gắn gợi ý từ danh mục."""

from __future__ import annotations

from ..schemas import Finding
from .catalog import Catalog

# Khi cùng một lỗi ở cùng dòng được nhiều nguồn báo, giữ nguồn đáng tin hơn
_SOURCE_PRIORITY = {"asan": 0, "ubsan": 0, "gcc": 1, "cppcheck": 2, "judge": 3, "custom_rule": 4}


def merge_findings(findings: list[Finding], catalog: Catalog) -> list[Finding]:
    best: dict[tuple[str, int | None], Finding] = {}
    for f in findings:
        if f.bug_pattern not in catalog:
            f = f.model_copy(update={"bug_pattern": "UNCLASSIFIED"})
        key = (f.bug_pattern, f.line)
        cur = best.get(key)
        if cur is None or (
            (_SOURCE_PRIORITY.get(f.source, 9), -f.confidence)
            < (_SOURCE_PRIORITY.get(cur.source, 9), -cur.confidence)
        ):
            best[key] = f
    # Bỏ lỗi không có số dòng nếu đã có lỗi cùng loại kèm số dòng
    with_line = {code for code, line in best if line is not None}
    merged = [f for (code, line), f in best.items() if line is not None or code not in with_line]
    for i, f in enumerate(merged):
        merged[i] = f.model_copy(update={"hint": catalog.get(f.bug_pattern).hint})
    return sorted(merged, key=lambda f: (f.line is None, f.line or 0, -f.confidence))
