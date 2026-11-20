"""Ontology OWL sinh từ YAML: đủ cá thể, không tham chiếu treo, khớp file trong repo."""

from datetime import datetime

import pytest
import yaml

from backend.app.config import ROOT
from backend.app.kg.model import KnowledgeBase
from backend.app.kg.owl import BASE, NS, build
from backend.app.schemas import Finding, GradingResult, Language, SubmissionReport, Verdict
from backend.app.storage import Storage

RDF = "{" + NS["rdf"] + "}"
OWL = "{" + NS["owl"] + "}"
CT = BASE + "#"


@pytest.fixture(scope="module")
def kb():
    return KnowledgeBase.load(ROOT / "knowledge", ROOT / "data" / "problems")


@pytest.fixture(scope="module")
def mined():
    return yaml.safe_load((ROOT / "knowledge" / "mined_rules.yaml").read_text("utf-8"))["rules"]


def individuals(tree):
    """{tên cá thể: (lớp, [(thuộc tính, đích)])}"""
    out = {}
    for e in tree.getroot():
        if e.tag != OWL + "NamedIndividual":
            continue
        name = e.get(RDF + "about").removeprefix(CT)
        cls = next(c.get(RDF + "resource") for c in e if c.tag == RDF + "type").removeprefix(CT)
        links = [
            (c.tag.removeprefix("{" + CT + "}"), c.get(RDF + "resource").removeprefix(CT))
            for c in e
            if c.tag.startswith("{" + CT) and c.get(RDF + "resource")
        ]
        out[name] = (cls, links)
    return out


def declared(tree):
    tags = {OWL + "Class", OWL + "ObjectProperty", OWL + "DatatypeProperty"}
    return {e.get(RDF + "about").removeprefix(CT) for e in tree.getroot() if e.tag in tags}


def test_every_kb_node_is_an_individual(kb, mined):
    ind = individuals(build(kb, mined))
    by_class = {}
    for name, (cls, _) in ind.items():
        by_class.setdefault(cls, set()).add(name)
    assert by_class["Concept"] == set(kb.concepts)
    assert by_class["BugPattern"] == set(kb.bug_patterns)
    assert by_class["Problem"] == set(kb.problems)
    actions = set().union(*(by_class.get(c, set()) for c in (
        "Explanation", "WorkedExample", "Visualization", "DebuggingExercise", "Exercise", "Quiz")))  # fmt: skip
    assert actions == set(kb.actions)
    rules = by_class["SuppressRule"] | by_class["AddRule"]
    assert rules == {r["id"] for r in mined}


def test_no_dangling_references(kb, mined):
    tree = build(kb, mined)
    ind, names = individuals(tree), declared(tree)
    for name, (cls, links) in ind.items():
        assert cls in names, name
        for prop, target in links:
            assert prop in names, (name, prop)
            assert target in ind, (name, prop, target)


def test_required_chain_and_inverse_data(kb, mined):
    ind = individuals(build(kb, mined))
    _, links = ind["MEM_LEAK"]
    remedies = {t for p, t in links if p == "remediatedBy"}
    assert remedies == {a.id for a in kb.actions.values() if "MEM_LEAK" in a.remediates}
    _, links = ind["MR029"]  # {NULL_DEREF, UNINIT_VAR} -> bỏ NULL_DEREF
    assert ind["MR029"][0] == "SuppressRule"
    assert ("concludes", "NULL_DEREF") in links and ("ifFound", "UNINIT_VAR") in links


def test_logs_give_student_code_exhibits_chain(kb, mined, tmp_path):
    st = Storage(tmp_path / "log.db")
    st.save(SubmissionReport(
        submission_id="s1", student_id="sv_a", problem_id="P002", language=Language.C,
        created_at=datetime.fromisoformat("2026-11-10T08:00:00+00:00"),
        grading=GradingResult(submission_id="s1", verdict=Verdict.WA, score=0, total=3),
        findings=[Finding(bug_pattern="MEM_LEAK", source="asan", line=3, message="leak")],
    ), "x")  # fmt: skip
    ind = individuals(build(kb, mined, tmp_path / "log.db"))
    assert ("submitted", "code_s1") in ind["student_sv_a"][1]
    assert ind["code_s1"][0] == "StudentCode"
    assert {("exhibits", "MEM_LEAK"), ("forProblem", "P002")} <= set(ind["code_s1"][1])


def test_committed_owl_is_up_to_date(kb, mined, tmp_path):
    out = tmp_path / "c_tutor.owl"
    build(kb, mined).write(out, encoding="utf-8", xml_declaration=True)
    committed = ROOT / "knowledge" / "ontology" / "c_tutor.owl"
    assert out.read_bytes() == committed.read_bytes(), (
        "knowledge/*.yaml đã đổi: chạy lại `python -m backend.app.kg.owl`"
    )
