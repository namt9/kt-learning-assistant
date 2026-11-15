"""Mô hình tri thức đọc từ knowledge/*.yaml và data/problems, kèm kiểm tra tính nhất quán.

Đây là "nguồn sự thật" của Knowledge Graph: nhóm sửa YAML, chạy kiểm tra, rồi nạp vào Neo4j
bằng `python -m backend.app.kg.load`. Lược đồ đồ thị mô tả trong docs/kg_schema.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from graphlib import CycleError, TopologicalSorter
from pathlib import Path

import yaml

from ..problems import ProblemRepository

ACTION_TYPES = {"GIAI_THICH", "VI_DU", "TRUC_QUAN", "GO_LOI", "BAI_TAP", "CAU_HOI"}
STYLES = {"visual", "verbal", "active", "reflective"}  # Felder–Silverman rút gọn 2 chiều


@dataclass(frozen=True)
class ConceptGroup:
    id: str
    name: str


@dataclass(frozen=True)
class Concept:
    id: str
    name: str
    group: str
    level: int
    description: str
    prerequisites: tuple[str, ...]


@dataclass(frozen=True)
class BugPatternNode:
    code: str
    name: str
    concepts: tuple[str, ...]
    detected_by: tuple[str, ...]
    hint: str


@dataclass(frozen=True)
class PedagogicalAction:
    id: str
    type: str
    title: str
    content: str
    teaches: tuple[str, ...]
    remediates: tuple[str, ...]
    styles: tuple[str, ...]
    level: int
    problem: str | None = None


@dataclass(frozen=True)
class ProblemNode:
    id: str
    title: str
    concepts: tuple[str, ...]


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class KnowledgeBase:
    groups: dict[str, ConceptGroup]
    concepts: dict[str, Concept]
    bug_patterns: dict[str, BugPatternNode]
    actions: dict[str, PedagogicalAction]
    problems: dict[str, ProblemNode]

    # ---------------------------------------------------------------- nạp

    @classmethod
    def load(cls, knowledge_dir: Path, problems_dir: Path) -> KnowledgeBase:
        def read(name: str) -> dict:
            return yaml.safe_load((knowledge_dir / name).read_text(encoding="utf-8"))

        c = read("concepts.yaml")
        groups = {g["id"]: ConceptGroup(g["id"], g["name"]) for g in c["groups"]}
        concepts = {
            x["id"]: Concept(
                id=x["id"],
                name=x["name"],
                group=x["group"],
                level=int(x.get("level", 1)),
                description=x.get("description", ""),
                prerequisites=tuple(x.get("prerequisites", [])),
            )
            for x in c["concepts"]
        }
        bugs = {
            b["code"]: BugPatternNode(
                code=b["code"],
                name=b["name"],
                concepts=tuple(b.get("concepts", [])),
                detected_by=tuple(b.get("detected_by", [])),
                hint=b.get("hint", ""),
            )
            for b in read("bug_patterns.yaml")["bug_patterns"]
        }
        actions = {
            a["id"]: PedagogicalAction(
                id=a["id"],
                type=a["type"],
                title=a["title"],
                content=a.get("content", ""),
                teaches=tuple(a.get("teaches", [])),
                remediates=tuple(a.get("remediates", [])),
                styles=tuple(a.get("styles", [])),
                level=int(a.get("level", 1)),
                problem=a.get("problem"),
            )
            for a in read("pedagogical_actions.yaml")["actions"]
        }
        problems = {
            p.id: ProblemNode(p.id, p.title, tuple(p.concepts))
            for p in ProblemRepository(problems_dir).list()
        }
        return cls(groups, concepts, bugs, actions, problems)

    # ---------------------------------------------------------------- truy vấn trong bộ nhớ

    def prerequisite_order(self) -> list[str]:
        """Thứ tự học hợp lệ: mọi khái niệm đứng sau các khái niệm tiên quyết của nó."""
        ts = TopologicalSorter({c.id: set(c.prerequisites) for c in self.concepts.values()})
        return list(ts.static_order())

    def depth(self) -> dict[str, int]:
        """Độ sâu = độ dài chuỗi tiên quyết dài nhất dẫn tới khái niệm (gốc = 0)."""
        d: dict[str, int] = {}
        for cid in self.prerequisite_order():
            pre = self.concepts[cid].prerequisites
            d[cid] = 1 + max((d[p] for p in pre), default=-1)
        return d

    def ancestors(self, concept_id: str) -> set[str]:
        seen: set[str] = set()
        stack = list(self.concepts[concept_id].prerequisites)
        while stack:
            cid = stack.pop()
            if cid not in seen:
                seen.add(cid)
                stack.extend(self.concepts[cid].prerequisites)
        return seen

    # ---------------------------------------------------------------- kiểm tra

    def validate(self) -> ValidationReport:
        r = ValidationReport()
        C, B, A, P = self.concepts, self.bug_patterns, self.actions, self.problems

        def need(kind: str, ref: str, pool, where: str):
            if ref not in pool:
                r.errors.append(f"{where}: {kind} '{ref}' không tồn tại")

        for c in C.values():
            need("nhóm", c.group, self.groups, f"concept {c.id}")
            for p in c.prerequisites:
                need("concept tiên quyết", p, C, f"concept {c.id}")
            if not 1 <= c.level <= 3:
                r.errors.append(f"concept {c.id}: level phải từ 1 đến 3")
        try:
            self.prerequisite_order()
        except CycleError as e:
            r.errors.append(f"quan hệ tiên quyết có chu trình: {' -> '.join(e.args[1])}")

        for b in B.values():
            for c in b.concepts:
                need("concept", c, C, f"bug {b.code}")
        for a in A.values():
            where = f"action {a.id}"
            if a.type not in ACTION_TYPES:
                r.errors.append(f"{where}: type '{a.type}' không hợp lệ")
            for s in a.styles:
                if s not in STYLES:
                    r.errors.append(f"{where}: style '{s}' không hợp lệ")
            for c in a.teaches:
                need("concept", c, C, where)
            for b in a.remediates:
                need("bug pattern", b, B, where)
            if a.problem:
                need("bài tập", a.problem, P, where)
            if not a.teaches:
                r.errors.append(f"{where}: phải dạy ít nhất một concept")
        for p in P.values():
            for c in p.concepts:
                need("concept", c, C, f"bài {p.id}")

        # Cảnh báo: chỗ còn thiếu nội dung (không chặn việc nạp)
        remediated = {b for a in A.values() for b in a.remediates}
        for b in B:
            if b not in remediated:
                r.errors.append(f"bug {b}: chưa có hành động sư phạm nào (REMEDIATED_BY)")
            elif b != "UNCLASSIFIED":
                styles = {s for a in A.values() if b in a.remediates for s in a.styles}
                if not ({"visual", "verbal"} <= styles and {"active", "reflective"} & styles):
                    r.warnings.append(f"bug {b}: hành động chưa đủ đa dạng phong cách học {styles}")
        taught = {c for a in A.values() for c in a.teaches}
        for c in C:
            if c not in taught:
                r.warnings.append(f"concept {c}: chưa có hành động nào dạy (TEACHES)")
        used = (
            {c for b in B.values() for c in b.concepts}
            | taught
            | {p for c in C.values() for p in c.prerequisites}
        )
        for c in C:
            if c not in used:
                r.warnings.append(f"concept {c}: chưa liên kết với lỗi, hành động hay concept nào")
        return r
