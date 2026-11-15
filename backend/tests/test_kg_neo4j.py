"""Nạp và truy vấn Knowledge Graph trên Neo4j THẬT.

Test XOÁ dữ liệu trong database, nên chỉ chạy với một Neo4j riêng cho test:

    docker run -d --name neo4j-test -p 7688:7687 -e NEO4J_AUTH=neo4j/testpassword neo4j:5
    NEO4J_TEST_URI=bolt://localhost:7688 pytest backend/tests/test_kg_neo4j.py

Không đặt NEO4J_TEST_URI thì các test này được bỏ qua.
"""

import os

import pytest

from backend.app.config import ROOT
from backend.app.kg.loader import load_static, load_submissions, reset
from backend.app.kg.model import KnowledgeBase
from backend.app.kg.queries import KGQueries
from backend.app.schemas import Finding, GradingResult, Language, SubmissionReport, Verdict
from backend.app.storage import Storage

URI = os.getenv("NEO4J_TEST_URI")
pytestmark = pytest.mark.skipif(not URI, reason="đặt NEO4J_TEST_URI để chạy test Neo4j")


@pytest.fixture(scope="module")
def kb():
    return KnowledgeBase.load(ROOT / "knowledge", ROOT / "data" / "problems")


@pytest.fixture(scope="module")
def driver():
    from neo4j import GraphDatabase

    auth = (os.getenv("NEO4J_TEST_USER", "neo4j"), os.getenv("NEO4J_TEST_PASSWORD", "testpassword"))
    with GraphDatabase.driver(URI, auth=auth) as d:
        d.verify_connectivity()
        yield d


def _report(sid, student, bugs, created):
    from datetime import datetime

    return SubmissionReport(
        submission_id=sid,
        student_id=student,
        problem_id="P002",
        language=Language.C,
        created_at=datetime.fromisoformat(created),
        grading=GradingResult(submission_id=sid, verdict=Verdict.WA, score=0, total=3),
        findings=[
            Finding(bug_pattern=b, source="asan", line=i + 1, message=b) for i, b in enumerate(bugs)
        ],
    )


@pytest.fixture(scope="module")
def loaded(driver, kb, tmp_path_factory):
    db = tmp_path_factory.mktemp("kg") / "log.db"
    st = Storage(db)
    # sv_a từng nhiều lần thiếu & trong scanf (khái niệm địa chỉ) rồi nay bị rò rỉ bộ nhớ
    st.save(_report("s1", "sv_a", ["SCANF_MISSING_AMP"], "2026-11-10T08:00:00+00:00"), "x")
    st.save(
        _report("s2", "sv_a", ["SCANF_MISSING_AMP", "UNINIT_VAR"], "2026-11-11T08:00:00+00:00"), "x"
    )
    st.save(_report("s3", "sv_b", ["OFF_BY_ONE"], "2026-11-11T09:00:00+00:00"), "x")
    with driver.session() as s:
        reset(s)
        counts = load_static(s, kb)
        n = load_submissions(s, db)
        # chạy lại lần hai: không được tạo trùng
        load_static(s, kb)
        load_submissions(s, db)
    return counts, n


def count(driver, cypher):
    return driver.execute_query(cypher).records[0][0]


def test_load_is_complete_and_idempotent(driver, kb, loaded):
    counts, n = loaded
    assert n == 3
    assert count(driver, "MATCH (c:Concept) RETURN count(c)") == len(kb.concepts)
    assert count(driver, "MATCH (b:BugPattern) RETURN count(b)") == len(kb.bug_patterns)
    assert count(driver, "MATCH (a:PedagogicalAction) RETURN count(a)") == len(kb.actions)
    assert count(driver, "MATCH ()-[r:PREREQUISITE_OF]->() RETURN count(r)") == counts["prereqs"]
    assert count(driver, "MATCH ()-[r:REMEDIATED_BY]->() RETURN count(r)") == counts["remediations"]
    assert count(driver, "MATCH ()-[r:EXHIBITS]->() RETURN count(r)") == 4
    # Không có chu trình tiên quyết trong đồ thị
    assert count(driver, "MATCH p=(c:Concept)-[:PREREQUISITE_OF*]->(c) RETURN count(p)") == 0


def test_assignment_graph_pattern_exists(driver, loaded):
    # Đề bài: [Student_Code] -> (Exhibits) -> [Bug_Pattern] -> (Remediated_By) -> [Pedagogical_Action]
    n = count(
        driver,
        "MATCH (:StudentCode)-[:EXHIBITS]->(:BugPattern)-[:REMEDIATED_BY]->(:PedagogicalAction) "
        "RETURN count(*)",
    )
    assert n > 0


def test_remediation_prefers_learning_style(driver, loaded):
    q = KGQueries(driver)
    visual = q.remediation("MEM_LEAK", ["visual"], limit=1)[0]
    active = q.remediation("MEM_LEAK", ["active"], limit=1)[0]
    assert "visual" in visual.styles and "active" in active.styles
    assert visual.id != active.id


def test_concepts_for_bugs(driver, loaded):
    rows = KGQueries(driver).concepts_for_bugs(["DANGLING_PTR"])
    ids = {r["id"] for r in rows}
    assert {"con_tro", "stack_heap"} <= ids
    assert all(r["prerequisites"] is not None for r in rows)


def test_weak_concepts_from_history(driver, loaded):
    weak = KGQueries(driver).student_weak_concepts("sv_a")
    assert weak[0]["id"] in {"nhap_xuat", "dia_chi", "truyen_tham_chieu"}
    assert weak[0]["weight"] == 2


def test_learning_path_reviews_weak_prerequisites_first(driver, kb, loaded):
    path = KGQueries(driver).learning_path("sv_a", ["MEM_LEAK"], ["visual"], max_steps=10)
    concepts = [s.concept for s in path.steps]
    reasons = {s.concept: s.reason for s in path.steps}
    # dia_chi là tiên quyết của cap_phat_dong và sv_a từng mắc lỗi liên quan -> phải ôn
    assert "dia_chi" in concepts and "Ôn" in reasons["dia_chi"]
    assert "cap_phat_dong" in concepts
    # thứ tự tôn trọng quan hệ tiên quyết
    depth = kb.depth()
    assert [depth[c] for c in concepts] == sorted(depth[c] for c in concepts)
    # không lặp hành động giữa các bước
    action_ids = [s.action_id for s in path.steps]
    assert len(action_ids) == len(set(action_ids))
    # khái niệm nền yếu được ôn bằng hành động sửa đúng lỗi sinh viên từng mắc
    remediates_history = {
        a.id for a in kb.actions.values() if {"SCANF_MISSING_AMP", "UNINIT_VAR"} & set(a.remediates)
    }
    for s in path.steps:
        if s.reason.startswith("Ôn"):
            assert s.action_id in remediates_history, s
    # sinh viên chưa có lịch sử: chỉ khái niệm của lỗi hiện tại
    fresh = KGQueries(driver).learning_path("sv_moi", ["MEM_LEAK"], [], max_steps=10)
    assert {s.concept for s in fresh.steps} <= set(kb.bug_patterns["MEM_LEAK"].concepts)
    assert all(s.action_id for s in fresh.steps)


def test_graph_export(driver, loaded, kb):
    g = KGQueries(driver).graph()
    labels = {n["label"] for n in g["nodes"]}
    assert labels == {"ConceptGroup", "Concept", "BugPattern", "PedagogicalAction", "Problem"}
    ids = {n["id"] for n in g["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in g["edges"])
    with_students = KGQueries(driver).graph(include_students=True)
    assert len(with_students["nodes"]) > len(g["nodes"])


def test_node_detail(driver, loaded):
    q = KGQueries(driver)
    bug = q.node("MEM_LEAK")
    assert bug["label"] == "BugPattern" and bug["props"]["name"]
    rels = {(link["dir"], link["type"]) for link in bug["links"]}
    assert ("out", "REMEDIATED_BY") in rels and ("out", "RELATED_TO") in rels
    code = q.node("s1")
    assert code["label"] == "StudentCode"
    assert code["props"]["created_at"].startswith("2026-11-10")  # DateTime -> chuỗi ISO
    assert ("in", "SUBMITTED") in {(link["dir"], link["type"]) for link in code["links"]}
    assert q.node("KHONG_TON_TAI") is None
