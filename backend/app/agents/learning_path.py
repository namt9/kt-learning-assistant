"""Learning-Path Agent: lộ trình sửa sai dựa trên Knowledge Graph.

Mặc định suy luận trên Neo4j (`KGQueries.learning_path`). Khi Neo4j không chạy, dùng cùng thuật toán
trên tri thức đọc từ YAML (`KnowledgeBase`) để demo không phụ thuộc vào Docker:

1. Khái niệm mục tiêu = khái niệm gắn với các lỗi hiện tại.
2. Thêm khái niệm tiên quyết (mọi cấp) của mục tiêu nếu sinh viên từng mắc lỗi liên quan.
3. Sắp theo độ sâu tiên quyết (nền trước). Mỗi khái niệm chọn một hành động sư phạm chưa dùng,
   ưu tiên: sửa lỗi hiện tại > sửa lỗi từng mắc ở khái niệm này > khớp phong cách học > dễ hơn.
"""

from __future__ import annotations

from ..kg.model import KnowledgeBase
from ..schemas import LearningPath, LearningStep

REASONS = {
    "weak_prerequisite": "Ôn khái niệm nền bạn từng mắc lỗi",
    "target": "Khái niệm gắn với lỗi vừa gặp",
}


class LearningPathAgent:
    def __init__(self, kb: KnowledgeBase, kg=None):
        self.kb = kb
        self.kg = kg

    def plan(
        self,
        student_id: str,
        bug_codes: list[str],
        styles: list[str],
        history_bugs: set[str],
        max_steps: int = 6,
    ) -> tuple[LearningPath, str | None]:
        """Trả về (lộ trình, ghi chú nếu phải dùng chế độ dự phòng)."""
        if self.kg is not None:
            try:
                return self.kg.learning_path(student_id, bug_codes, styles, max_steps), None
            except Exception as e:  # Neo4j lỗi giữa chừng: vẫn trả lộ trình
                note = f"Lỗi truy vấn KG ({e}), dùng tri thức YAML."
        else:
            note = "Neo4j không chạy, dùng tri thức YAML."
        return self.offline(student_id, bug_codes, styles, history_bugs, max_steps), note

    def offline(self, student_id, bug_codes, styles, history_bugs, max_steps=6) -> LearningPath:
        kb, depth = self.kb, self.kb.depth()
        concepts_of = lambda b: kb.bug_patterns[b].concepts if b in kb.bug_patterns else ()  # noqa: E731
        targets = {c for b in bug_codes for c in concepts_of(b)}
        weak = {c for b in history_bugs for c in concepts_of(b)}
        weak_prereqs = {p for t in targets for p in kb.ancestors(t) if p in weak} - targets
        items = [(c, "target") for c in targets] + [(c, "weak_prerequisite") for c in weak_prereqs]
        items.sort(key=lambda it: (depth[it[0]], it[1] != "weak_prerequisite", it[0]))

        steps, used = [], set()
        for concept, reason in items:

            def rank(a, concept=concept):
                fixes_history = any(
                    b in history_bugs and concept in concepts_of(b) for b in a.remediates
                )
                return (
                    -bool(set(a.remediates) & set(bug_codes)),
                    -fixes_history,
                    -len(set(a.styles) & set(styles)),
                    a.level,
                    a.id,
                )

            candidates = sorted((a for a in kb.actions.values() if concept in a.teaches), key=rank)
            best = next((a for a in candidates if a.id not in used), None)
            if best is None:
                continue
            used.add(best.id)
            steps.append(LearningStep(
                concept=concept, action=best.title, action_id=best.id, action_type=best.type,
                resource=best.problem, reason=REASONS[reason],
            ))  # fmt: skip
            if len(steps) == max_steps:
                break
        return LearningPath(student_id=student_id, steps=steps, source="offline")
