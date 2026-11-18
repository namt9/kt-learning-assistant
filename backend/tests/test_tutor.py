"""Orchestrator, hồ sơ sinh viên, bảng hỏi phong cách học và Learning-Path Agent (dự phòng)."""

from datetime import datetime, timedelta

import pytest

from backend.app.agents.learning_path import LearningPathAgent
from backend.app.config import ROOT
from backend.app.kg.model import KnowledgeBase
from backend.app.schemas import Finding, GradingResult, Language, SubmissionReport, Verdict
from backend.app.student.profile import QUESTIONNAIRE, build_profile, score_questionnaire


@pytest.fixture(scope="module")
def kb():
    return KnowledgeBase.load(ROOT / "knowledge", ROOT / "data" / "problems")


T0 = datetime.fromisoformat("2026-11-18T08:00:00+00:00")


def rep(i, problem, verdict, bugs=(), suppressed=()):
    findings = [Finding(bug_pattern=b, source="gcc", line=1, message=b) for b in bugs]
    findings += [Finding(bug_pattern=b, source="asan", line=2, message=b, suppressed_by="MR1")
                 for b in suppressed]  # fmt: skip
    return SubmissionReport(
        submission_id=f"s{i}", student_id="sv", problem_id=problem, language=Language.C,
        created_at=T0 + timedelta(minutes=i),
        grading=GradingResult(submission_id=f"s{i}", verdict=verdict, score=0), findings=findings,
    )  # fmt: skip


# ------------------------------------------------------------ phong cách học


def test_questionnaire_scoring():
    all_a = {q["id"]: "a" for q in QUESTIONNAIRE}
    assert score_questionnaire(all_a) == ["visual", "active"]
    mixed = {**all_a, "vv1": "b", "vv2": "b", "ar3": "b"}
    assert score_questionnaire(mixed) == ["verbal", "active"]  # đa số 2/3 mỗi chiều
    with pytest.raises(ValueError):
        score_questionnaire({"vv1": "a"})


# ------------------------------------------------------------ hồ sơ năng lực


def test_profile_mastery(kb):
    reports = [
        rep(0, "P001", Verdict.WA, ["UNINIT_VAR"], suppressed=["NULL_DEREF"]),
        rep(1, "P001", Verdict.AC),
    ]
    p = build_profile("sv", reports, kb, ["visual"])
    m = {c.concept: c for c in p.concepts}
    assert p.submissions == 2 and p.accepted == 1 and p.styles == ["visual"]
    assert m["khoi_tao"].mastery < 0.5 < m["mang"].mastery  # lỗi kéo xuống, AC kéo lên
    # cảnh báo hệ quả bị khử không tính là lỗi sinh viên mắc
    assert not any(c in m for c in kb.bug_patterns["NULL_DEREF"].concepts if c != "mang")
    assert [b["bug"] for b in p.top_bugs] == ["UNINIT_VAR"]
    groups = {g.group: g for g in p.groups}
    assert len(groups) == len(kb.groups)
    assert groups[kb.concepts["khoi_tao"].group].mastery is not None
    assert any(g.mastery is None for g in p.groups)  # nhóm chưa có bằng chứng


def test_recent_submissions_weigh_more(kb):
    improving = [rep(0, "P001", Verdict.WA, ["UNINIT_VAR"]), rep(1, "P003", Verdict.AC)]
    declining = [rep(0, "P003", Verdict.AC), rep(1, "P001", Verdict.WA, ["UNINIT_VAR"])]
    m = lambda rs: {c.concept: c.mastery for c in build_profile("sv", rs, kb, None).concepts}  # noqa: E731
    assert m(improving)["khoi_tao"] > m(declining)["khoi_tao"]


def test_empty_profile(kb):
    p = build_profile("moi", [], kb, None)
    assert p.concepts == [] and all(g.mastery is None for g in p.groups) and p.styles is None


# ------------------------------------------------------------ lộ trình (không cần Neo4j)


def test_offline_learning_path_reviews_weak_prerequisites(kb):
    agent = LearningPathAgent(kb, kg=None)
    path, note = agent.plan("sv", ["MEM_LEAK"], ["visual"], {"SCANF_MISSING_AMP", "UNINIT_VAR"},
                            max_steps=10)  # fmt: skip
    assert path.source == "offline" and "Neo4j" in note
    concepts = [s.concept for s in path.steps]
    assert "dia_chi" in concepts and "cap_phat_dong" in concepts
    reasons = {s.concept: s.reason for s in path.steps}
    assert reasons["dia_chi"].startswith("Ôn")
    depth = kb.depth()
    assert [depth[c] for c in concepts] == sorted(depth[c] for c in concepts)
    ids = [s.action_id for s in path.steps]
    assert len(ids) == len(set(ids))
    fresh, _ = agent.plan("moi", ["MEM_LEAK"], [], set(), max_steps=10)
    assert {s.concept for s in fresh.steps} <= set(kb.bug_patterns["MEM_LEAK"].concepts)


def test_learning_path_falls_back_when_kg_query_fails(kb):
    class BrokenKG:
        def learning_path(self, *a, **k):
            raise RuntimeError("mất kết nối")

    path, note = LearningPathAgent(kb, BrokenKG()).plan("sv", ["OFF_BY_ONE"], [], set())
    assert path.source == "offline" and path.steps and "mất kết nối" in note


# ------------------------------------------------------------ API v1


MISSING_AMP = (
    '#include <stdio.h>\nint main(void){int n; scanf("%d", n); printf("%d\\n", n); return 0;}'
)


def test_tutor_submit_full_flow(client):
    body = {"student_id": "sv_t", "problem_id": "P001", "source_code": MISSING_AMP}
    r = client.post("/tutor/submit", json=body)
    assert r.status_code == 200, r.text
    res = r.json()
    agents = [s["agent"] for s in res["trace"]]
    assert agents == ["grading", "mined_rules", "knowledge_graph", "diagnosis", "learning_path"]
    status = {s["agent"]: s["status"] for s in res["trace"]}
    assert status["knowledge_graph"] == "skipped"  # test không dùng Neo4j
    # yêu cầu hybrid nhưng test không có LLM -> lùi về giải thích bằng luật
    assert status["diagnosis"] == "fallback" and res["diagnosis"]["mode"] == "rule"
    assert status["learning_path"] == "fallback" and res["learning_path"]["source"] == "offline"
    assert res["learning_path"]["steps"]
    primary = {f["bug_pattern"] for f in res["report"]["findings"] if not f["suppressed_by"]}
    assert "SCANF_MISSING_AMP" in primary
    assert {it["bug_pattern"] for it in res["diagnosis"]["items"]} == primary

    prof = client.get("/students/sv_t/profile").json()
    assert prof["submissions"] == 1 and prof["concepts"]
    kinds = [i["kind"] for i in client.get("/students/sv_t/interactions").json()]
    assert kinds[:2] == ["diagnosis", "submit"]  # mới nhất trước


def test_tutor_submit_validation(client):
    bad = {"student_id": "sv", "problem_id": "P999", "source_code": "int main(){}"}
    assert client.post("/tutor/submit", json=bad).status_code == 404


def test_learning_style_api(client):
    qs = client.get("/learning-style/questionnaire").json()
    assert len(qs) == 6 and {"id", "text", "a", "b"} <= set(qs[0])
    answers = {q["id"]: "b" for q in qs}
    r = client.put("/students/sv_s/learning-style", json=answers).json()
    assert r["styles"] == ["verbal", "reflective"]
    assert client.get("/students/sv_s/profile").json()["styles"] == ["verbal", "reflective"]
    assert client.put("/students/sv_s/learning-style", json={"vv1": "c"}).status_code == 422
