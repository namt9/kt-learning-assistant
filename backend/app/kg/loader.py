"""Nạp Knowledge Graph vào Neo4j (idempotent: chạy lại nhiều lần không tạo trùng).

Phần tĩnh   : ConceptGroup, Concept, BugPattern, PedagogicalAction, Problem và quan hệ giữa chúng.
Phần động   : Student, StudentCode và (StudentCode)-[:EXHIBITS]->(BugPattern) từ log SQLite của v0.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .model import KnowledgeBase

LABELS = ["ConceptGroup", "Concept", "BugPattern", "PedagogicalAction", "Problem", "Student",
          "StudentCode"]  # fmt: skip

_CONSTRAINTS = [
    f"CREATE CONSTRAINT {label.lower()}_id IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE"
    for label in LABELS
]


def _rows_static(kb: KnowledgeBase) -> dict[str, list[dict]]:
    return {
        "groups": [{"id": g.id, "name": g.name} for g in kb.groups.values()],
        "concepts": [
            {
                "id": c.id,
                "name": c.name,
                "group": c.group,
                "level": c.level,
                "description": c.description,
                "depth": kb.depth()[c.id],
            }
            for c in kb.concepts.values()
        ],
        "prereqs": [{"from": p, "to": c.id} for c in kb.concepts.values() for p in c.prerequisites],
        "bugs": [
            {
                "id": b.code,
                "name": b.name,
                "hint": b.hint,
                "detected_by": list(b.detected_by),
            }
            for b in kb.bug_patterns.values()
        ],
        "bug_concepts": [
            {"bug": b.code, "concept": c} for b in kb.bug_patterns.values() for c in b.concepts
        ],
        "actions": [
            {
                "id": a.id,
                "type": a.type,
                "title": a.title,
                "content": a.content,
                "styles": list(a.styles),
                "level": a.level,
            }
            for a in kb.actions.values()
        ],
        "remediations": [
            {"bug": b, "action": a.id} for a in kb.actions.values() for b in a.remediates
        ],
        "teaches": [{"action": a.id, "concept": c} for a in kb.actions.values() for c in a.teaches],
        "action_problems": [
            {"action": a.id, "problem": a.problem} for a in kb.actions.values() if a.problem
        ],
        "problems": [{"id": p.id, "title": p.title} for p in kb.problems.values()],
        "practices": [
            {"problem": p.id, "concept": c} for p in kb.problems.values() for c in p.concepts
        ],
    }


_STATIC_CYPHER = [
    ("groups", "UNWIND $rows AS r MERGE (g:ConceptGroup {id: r.id}) SET g.name = r.name"),
    (
        "concepts",
        """UNWIND $rows AS r
        MERGE (c:Concept {id: r.id})
        SET c.name = r.name, c.level = r.level, c.description = r.description, c.depth = r.depth
        WITH c, r MATCH (g:ConceptGroup {id: r.group}) MERGE (c)-[:PART_OF]->(g)""",
    ),
    (
        "prereqs",
        """UNWIND $rows AS r
        MATCH (a:Concept {id: r.from}), (b:Concept {id: r.to})
        MERGE (a)-[:PREREQUISITE_OF]->(b)""",
    ),
    (
        "bugs",
        """UNWIND $rows AS r MERGE (b:BugPattern {id: r.id})
        SET b.name = r.name, b.hint = r.hint, b.detected_by = r.detected_by""",
    ),
    (
        "bug_concepts",
        """UNWIND $rows AS r
        MATCH (b:BugPattern {id: r.bug}), (c:Concept {id: r.concept})
        MERGE (b)-[:RELATED_TO]->(c)""",
    ),
    (
        "actions",
        """UNWIND $rows AS r MERGE (a:PedagogicalAction {id: r.id})
        SET a.type = r.type, a.title = r.title, a.content = r.content,
            a.styles = r.styles, a.level = r.level""",
    ),
    (
        "remediations",
        """UNWIND $rows AS r
        MATCH (b:BugPattern {id: r.bug}), (a:PedagogicalAction {id: r.action})
        MERGE (b)-[:REMEDIATED_BY]->(a)""",
    ),
    (
        "teaches",
        """UNWIND $rows AS r
        MATCH (a:PedagogicalAction {id: r.action}), (c:Concept {id: r.concept})
        MERGE (a)-[:TEACHES]->(c)""",
    ),
    ("problems", "UNWIND $rows AS r MERGE (p:Problem {id: r.id}) SET p.title = r.title"),
    (
        "practices",
        """UNWIND $rows AS r
        MATCH (p:Problem {id: r.problem}), (c:Concept {id: r.concept})
        MERGE (p)-[:PRACTICES]->(c)""",
    ),
    (
        "action_problems",
        """UNWIND $rows AS r
        MATCH (a:PedagogicalAction {id: r.action}), (p:Problem {id: r.problem})
        MERGE (a)-[:USES_PROBLEM]->(p)""",
    ),
]

# Xoá các quan hệ tĩnh trước khi nạp lại để quan hệ bị bỏ khỏi YAML cũng biến mất khỏi đồ thị
_CLEAR_STATIC_RELS = """
MATCH (:Concept|BugPattern|PedagogicalAction|Problem)
      -[r:PART_OF|PREREQUISITE_OF|RELATED_TO|REMEDIATED_BY|TEACHES|PRACTICES|USES_PROBLEM]->()
DELETE r
"""


def load_static(session, kb: KnowledgeBase) -> dict[str, int]:
    for stmt in _CONSTRAINTS:
        session.run(stmt).consume()
    session.run(_CLEAR_STATIC_RELS).consume()
    rows = _rows_static(kb)
    for key, cypher in _STATIC_CYPHER:
        session.run(cypher, rows=rows[key]).consume()
    return {k: len(v) for k, v in rows.items()}


def load_submissions(session, db_path: Path) -> int:
    """Đưa log nộp bài v0 vào đồ thị: Student-SUBMITTED->StudentCode-EXHIBITS->BugPattern."""
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        subs = [dict(r) for r in conn.execute(
            "SELECT id, student_id, problem_id, language, verdict, score, created_at "
            "FROM submissions"
        )]  # fmt: skip
        finds = [dict(r) for r in conn.execute(
            "SELECT submission_id, bug_pattern, source, line, message, confidence FROM findings"
        )]  # fmt: skip
    finally:
        conn.close()
    session.run(
        """UNWIND $rows AS r
        MERGE (s:Student {id: r.student_id})
        MERGE (c:StudentCode {id: r.id})
        SET c.language = r.language, c.verdict = r.verdict, c.score = r.score,
            c.created_at = datetime(r.created_at)
        MERGE (s)-[:SUBMITTED]->(c)
        WITH c, r MATCH (p:Problem {id: r.problem_id}) MERGE (c)-[:FOR_PROBLEM]->(p)""",
        rows=subs,
    ).consume()
    session.run(
        """UNWIND $rows AS r
        MATCH (c:StudentCode {id: r.submission_id}), (b:BugPattern {id: r.bug_pattern})
        MERGE (c)-[e:EXHIBITS {line: coalesce(r.line, -1), source: r.source}]->(b)
        SET e.message = r.message, e.confidence = r.confidence""",
        rows=finds,
    ).consume()
    return len(subs)


def reset(session) -> None:
    """Xoá toàn bộ node do hệ thống tạo (chỉ dùng khi phát triển)."""
    session.run(f"MATCH (n:{'|'.join(LABELS)}) DETACH DELETE n").consume()
