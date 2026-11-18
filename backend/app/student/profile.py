"""Hồ sơ năng lực và phong cách học của sinh viên.

Mức thành thạo tính từ log nộp bài, không cần Neo4j, dùng tri thức đọc từ YAML (KnowledgeBase):

- bài AC        -> thành công cho các khái niệm bài tập đó luyện (trừ khái niệm vẫn mắc lỗi);
- mỗi lỗi gốc   -> thất bại cho các khái niệm gắn với lỗi (cảnh báo hệ quả bị bỏ qua);
- lần nộp thứ k tính từ lần mới nhất có trọng số DECAY^k, để hồ sơ phản ánh tiến bộ gần đây;
- mastery = (thành công + 1) / (thành công + thất bại + 2): làm trơn Laplace, chưa có dữ liệu = 0.5.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from ..kg.model import KnowledgeBase
from ..schemas import (
    ConceptMastery,
    GroupMastery,
    StudentProfile,
    StyleDimension,
    SubmissionReport,
    Verdict,
)

DECAY = 0.85

# Bảng hỏi rút gọn theo mô hình Felder–Silverman, 2 chiều x 3 câu (nhóm tự soạn).
# Mỗi lựa chọn "a"/"b" ứng với một cực của chiều đó.
QUESTIONNAIRE = [
    {"id": "vv1", "dimension": "visual_verbal",
     "text": "Khi học một khái niệm mới như con trỏ, bạn dễ hiểu hơn nhờ:",
     "a": ("visual", "Hình vẽ các ô nhớ và mũi tên"),
     "b": ("verbal", "Lời giải thích và định nghĩa bằng chữ")},
    {"id": "vv2", "dimension": "visual_verbal",
     "text": "Sau một buổi học, điều bạn nhớ rõ nhất là:",
     "a": ("visual", "Sơ đồ, hình ảnh trên slide"),
     "b": ("verbal", "Những gì thầy cô giảng và ghi chú")},
    {"id": "vv3", "dimension": "visual_verbal",
     "text": "Tài liệu lập trình bạn thích đọc là:",
     "a": ("visual", "Có nhiều sơ đồ, bảng, hình minh họa"),
     "b": ("verbal", "Có đoạn giải thích chi tiết, mạch lạc")},
    {"id": "ar1", "dimension": "active_reflective",
     "text": "Khi gặp một bài tập mới, bạn thường:",
     "a": ("active", "Viết code thử ngay rồi sửa dần"),
     "b": ("reflective", "Nghĩ kỹ cách giải rồi mới viết")},
    {"id": "ar2", "dimension": "active_reflective",
     "text": "Bạn học tốt hơn khi:",
     "a": ("active", "Tự làm bài tập, chạy thử ví dụ"),
     "b": ("reflective", "Đọc, tự ngẫm và tóm tắt lại")},
    {"id": "ar3", "dimension": "active_reflective",
     "text": "Khi chương trình chạy sai, bạn thường:",
     "a": ("active", "Thử sửa vài chỗ rồi chạy lại"),
     "b": ("reflective", "Đọc kỹ code, lần theo từng dòng")},
]  # fmt: skip


def score_questionnaire(answers: dict[str, str]) -> list[str]:
    """answers: {id câu: "a"|"b"} -> phong cách nổi trội của mỗi chiều (đa số trong 3 câu)."""
    votes: dict[str, Counter] = defaultdict(Counter)
    for q in QUESTIONNAIRE:
        choice = answers.get(q["id"])
        if choice not in ("a", "b"):
            raise ValueError(f"câu {q['id']} cần trả lời 'a' hoặc 'b'")
        votes[q["dimension"]][q[choice][0]] += 1
    return [votes[dim].most_common(1)[0][0] for dim in ("visual_verbal", "active_reflective")]


def build_profile(
    student_id: str,
    reports: list[SubmissionReport],
    kb: KnowledgeBase,
    styles: list[str] | None,
    style_detail: list[StyleDimension] | None = None,
) -> StudentProfile:
    success: dict[str, float] = defaultdict(float)
    error: dict[str, float] = defaultdict(float)
    bug_times: Counter = Counter()
    n = len(reports)
    for i, rep in enumerate(reports):
        w = DECAY ** (n - 1 - i)
        primary = {f.bug_pattern for f in rep.findings if not f.suppressed_by}
        bug_times.update(primary)
        wrong = {c for b in primary if b in kb.bug_patterns for c in kb.bug_patterns[b].concepts}
        for c in wrong:
            error[c] += w
        problem = kb.problems.get(rep.problem_id)
        if rep.grading.verdict == Verdict.AC and problem:
            for c in set(problem.concepts) - wrong:
                success[c] += w

    concepts = []
    for cid in sorted(set(success) | set(error)):
        if cid not in kb.concepts:
            continue
        s, e = success[cid], error[cid]
        c = kb.concepts[cid]
        concepts.append(ConceptMastery(
            concept=cid, name=c.name, group=c.group, mastery=round((s + 1) / (s + e + 2), 3),
            evidence=round(s + e, 3), successes=round(s, 3), errors=round(e, 3),
        ))  # fmt: skip
    concepts.sort(key=lambda m: (m.mastery, -m.evidence))

    groups = []
    for gid, g in kb.groups.items():
        mine = [m for m in concepts if m.group == gid]
        weight = sum(m.evidence for m in mine)
        avg = sum(m.mastery * m.evidence for m in mine) / weight if weight else None
        groups.append(GroupMastery(group=gid, name=g.name, concepts=len(mine),
                                   mastery=None if avg is None else round(avg, 3)))  # fmt: skip

    return StudentProfile(
        student_id=student_id,
        styles=styles,
        style_detail=style_detail or [],
        submissions=n,
        accepted=sum(r.grading.verdict == Verdict.AC for r in reports),
        concepts=concepts,
        groups=groups,
        top_bugs=[
            {"bug": b, "name": kb.bug_patterns[b].name if b in kb.bug_patterns else b, "times": t}
            for b, t in bug_times.most_common(5)
        ],
    )
