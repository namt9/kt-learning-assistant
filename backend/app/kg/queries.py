"""Truy vấn Knowledge Graph trên Neo4j cho các agent và giao diện.

- Diagnosis Agent    : concepts_for_bugs, remediation
- Learning-Path Agent: student_weak_concepts, learning_path
- KG viewer (E)      : graph
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from ..schemas import LearningPath, LearningStep


@dataclass
class RemediationAction:
    id: str
    type: str
    title: str
    content: str
    styles: list[str]
    level: int
    style_match: int
    problem: str | None


def connect():
    """Mở driver Neo4j theo biến môi trường NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD."""
    from neo4j import GraphDatabase

    return GraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "change-me")),
    )


class KGQueries:
    def __init__(self, driver, database: str | None = None):
        self.driver = driver
        self.database = database

    def _run(self, cypher: str, **params) -> list[dict]:
        records, _, _ = self.driver.execute_query(cypher, params, database_=self.database)
        return [r.data() for r in records]

    # ------------------------------------------------------------ chẩn đoán

    def concepts_for_bugs(self, bug_codes: list[str]) -> list[dict]:
        """Khái niệm liên quan tới các lỗi, kèm khái niệm tiên quyết trực tiếp."""
        return self._run(
            """
            MATCH (b:BugPattern)-[:RELATED_TO]->(c:Concept)
            WHERE b.id IN $codes
            OPTIONAL MATCH (p:Concept)-[:PREREQUISITE_OF]->(c)
            WITH c, collect(DISTINCT b.id) AS bugs, collect(DISTINCT p.id) AS prerequisites
            RETURN c.id AS id, c.name AS name, c.level AS level, c.depth AS depth,
                   bugs, prerequisites
            ORDER BY depth, id
            """,
            codes=bug_codes,
        )

    def remediation(
        self, bug_code: str, styles: list[str] | None = None, limit: int = 3
    ) -> list[RemediationAction]:
        """Hành động sửa lỗi, ưu tiên khớp phong cách học rồi tới mức độ dễ."""
        rows = self._run(
            """
            MATCH (:BugPattern {id: $code})-[:REMEDIATED_BY]->(a:PedagogicalAction)
            OPTIONAL MATCH (a)-[:USES_PROBLEM]->(p:Problem)
            WITH a, p, size([s IN a.styles WHERE s IN $styles]) AS style_match
            RETURN a.id AS id, a.type AS type, a.title AS title, a.content AS content,
                   a.styles AS styles, a.level AS level, style_match, p.id AS problem
            ORDER BY style_match DESC, level ASC, id ASC
            LIMIT $limit
            """,
            code=bug_code,
            styles=styles or [],
            limit=limit,
        )
        return [RemediationAction(**r) for r in rows]

    # ------------------------------------------------------------ hồ sơ & lộ trình

    def student_bug_counts(self, student_id: str) -> list[dict]:
        return self._run(
            """
            MATCH (:Student {id: $sid})-[:SUBMITTED]->(:StudentCode)-[:EXHIBITS]->(b:BugPattern)
            RETURN b.id AS bug, b.name AS name, count(*) AS times
            ORDER BY times DESC, bug
            """,
            sid=student_id,
        )

    def student_weak_concepts(self, student_id: str, limit: int = 10) -> list[dict]:
        """Khái niệm yếu = khái niệm gắn với các lỗi sinh viên mắc nhiều lần."""
        return self._run(
            """
            MATCH (:Student {id: $sid})-[:SUBMITTED]->(:StudentCode)-[:EXHIBITS]->(b:BugPattern)
                  -[:RELATED_TO]->(c:Concept)
            RETURN c.id AS id, c.name AS name, c.depth AS depth, count(*) AS weight,
                   collect(DISTINCT b.id) AS bugs
            ORDER BY weight DESC, depth ASC, id
            LIMIT $limit
            """,
            sid=student_id,
            limit=limit,
        )

    def learning_path(
        self,
        student_id: str,
        bug_codes: list[str],
        styles: list[str] | None = None,
        max_steps: int = 6,
    ) -> LearningPath:
        """Lộ trình sửa sai: ôn khái niệm nền còn yếu trước, rồi tới khái niệm gắn với lỗi hiện tại.

        1. Khái niệm mục tiêu = RELATED_TO của các lỗi hiện tại.
        2. Thêm khái niệm tiên quyết (mọi cấp) của mục tiêu nếu sinh viên từng mắc lỗi liên quan.
        3. Sắp theo độ sâu tiên quyết (nền trước), rồi mỗi khái niệm chọn một hành động TEACHES
           ưu tiên: sửa đúng lỗi hiện tại > khớp phong cách học > dễ hơn.
        """
        rows = self._run(
            """
            MATCH (b:BugPattern)-[:RELATED_TO]->(t:Concept) WHERE b.id IN $codes
            WITH collect(DISTINCT t) AS targets
            OPTIONAL MATCH (:Student {id: $sid})-[:SUBMITTED]->(:StudentCode)-[:EXHIBITS]->
                           (:BugPattern)-[:RELATED_TO]->(w:Concept)
            WITH targets, collect(DISTINCT w) AS weak
            UNWIND targets AS t
            OPTIONAL MATCH (pre:Concept)-[:PREREQUISITE_OF*1..]->(t) WHERE pre IN weak
            WITH targets, collect(DISTINCT pre) AS weak_prereqs
            WITH [c IN targets | {c: c, reason: 'target'}] +
                 [c IN weak_prereqs WHERE NOT c IN targets | {c: c, reason: 'weak_prerequisite'}]
                 AS items
            UNWIND items AS item
            WITH item.c AS c, item.reason AS reason
            MATCH (a:PedagogicalAction)-[:TEACHES]->(c)
            OPTIONAL MATCH (a)-[:USES_PROBLEM]->(p:Problem)
            WITH c, reason, a, p,
                 CASE WHEN EXISTS { (b:BugPattern)-[:REMEDIATED_BY]->(a) WHERE b.id IN $codes }
                      THEN 1 ELSE 0 END AS fixes_bug,
                 size([s IN a.styles WHERE s IN $styles]) AS style_match
            ORDER BY fixes_bug DESC, style_match DESC, a.level ASC, a.id ASC
            WITH c, reason, collect({id: a.id, type: a.type, title: a.title,
                                     problem: p.id})[0] AS best
            RETURN c.id AS concept, c.name AS concept_name, c.depth AS depth, reason, best
            ORDER BY depth ASC, CASE reason WHEN 'weak_prerequisite' THEN 0 ELSE 1 END, concept
            LIMIT $max_steps
            """,
            sid=student_id,
            codes=bug_codes,
            styles=styles or [],
            max_steps=max_steps,
        )
        steps = [
            LearningStep(
                concept=r["concept"],
                action=r["best"]["title"],
                action_id=r["best"]["id"],
                action_type=r["best"]["type"],
                resource=r["best"]["problem"],
                reason=(
                    "Ôn khái niệm nền bạn từng mắc lỗi"
                    if r["reason"] == "weak_prerequisite"
                    else "Khái niệm gắn với lỗi vừa gặp"
                ),
            )
            for r in rows
        ]
        return LearningPath(student_id=student_id, steps=steps)

    # ------------------------------------------------------------ trực quan hoá

    def graph(self, include_students: bool = False) -> dict:
        """Toàn bộ đồ thị dạng {nodes, edges} cho KG viewer (pyvis / Cytoscape.js)."""
        labels = ["ConceptGroup", "Concept", "BugPattern", "PedagogicalAction", "Problem"]
        if include_students:
            labels += ["Student", "StudentCode"]
        nodes = self._run(
            """
            MATCH (n) WHERE any(l IN labels(n) WHERE l IN $labels)
            RETURN n.id AS id, labels(n)[0] AS label,
                   coalesce(n.name, n.title, n.verdict, n.id) AS name
            """,
            labels=labels,
        )
        edges = self._run(
            """
            MATCH (a)-[r]->(b)
            WHERE any(l IN labels(a) WHERE l IN $labels) AND any(l IN labels(b) WHERE l IN $labels)
            RETURN a.id AS source, b.id AS target, type(r) AS type
            """,
            labels=labels,
        )
        return {"nodes": nodes, "edges": edges}
