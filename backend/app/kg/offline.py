"""Tri thức KG đọc từ YAML, cùng giao diện với KGQueries cho phần Diagnosis Agent cần.

Dùng khi Neo4j không chạy (demo, script đánh giá): kết quả xếp hạng giống hệt truy vấn Cypher
`KGQueries.remediation` (khớp phong cách học, rồi dễ trước, rồi theo id).
"""

from __future__ import annotations

from .model import KnowledgeBase
from .queries import RemediationAction


class OfflineKG:
    def __init__(self, kb: KnowledgeBase):
        self.kb = kb

    def concepts_for_bugs(self, bug_codes: list[str]) -> list[dict]:
        depth = self.kb.depth()
        ids = {c for b in bug_codes if b in self.kb.bug_patterns
               for c in self.kb.bug_patterns[b].concepts}  # fmt: skip
        rows = []
        for cid in ids:
            c = self.kb.concepts[cid]
            rows.append({
                "id": cid, "name": c.name, "level": c.level, "depth": depth[cid],
                "bugs": [b for b in bug_codes if b in self.kb.bug_patterns
                         and cid in self.kb.bug_patterns[b].concepts],
                "prerequisites": list(c.prerequisites),
            })  # fmt: skip
        return sorted(rows, key=lambda r: (r["depth"], r["id"]))

    def remediation(self, bug_code: str, styles: list[str] | None = None, limit: int = 3):
        styles = styles or []
        acts = [a for a in self.kb.actions.values() if bug_code in a.remediates]
        acts.sort(key=lambda a: (-len(set(a.styles) & set(styles)), a.level, a.id))
        return [
            RemediationAction(
                id=a.id, type=a.type, title=a.title, content=a.content, styles=list(a.styles),
                level=a.level, style_match=len(set(a.styles) & set(styles)), problem=a.problem,
            )
            for a in acts[:limit]
        ]  # fmt: skip
