"""Kiểm tra tri thức trong knowledge/*.yaml (không cần Neo4j)."""

from pathlib import Path

import pytest
import yaml

from backend.app.config import ROOT
from backend.app.kg.model import KnowledgeBase


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    return KnowledgeBase.load(ROOT / "knowledge", ROOT / "data" / "problems")


def test_knowledge_is_consistent(kb):
    report = kb.validate()
    assert report.ok, report.errors


def test_required_concept_groups_from_assignment(kb):
    # Đề bài: concept map về Biến, Con trỏ, Cấu trúc dữ liệu, Quản lý bộ nhớ
    groups = {c.group for c in kb.concepts.values()}
    assert {"nhom_bien", "nhom_con_tro", "nhom_ctdl", "nhom_bo_nho"} <= groups


def test_every_bug_pattern_links_to_concepts_and_actions(kb):
    for b in kb.bug_patterns.values():
        if b.code != "UNCLASSIFIED":
            assert b.concepts, b.code
        assert any(b.code in a.remediates for a in kb.actions.values()), b.code


def test_prerequisite_order_and_depth(kb):
    order = kb.prerequisite_order()
    pos = {c: i for i, c in enumerate(order)}
    for c in kb.concepts.values():
        for p in c.prerequisites:
            assert pos[p] < pos[c.id]
    depth = kb.depth()
    assert depth["cu_phap"] == 0
    assert depth["cap_phat_dong"] > depth["con_tro"] > depth["bien"]
    assert {"con_tro", "dia_chi", "bien", "cu_phap"} <= kb.ancestors("cap_phat_dong")


def _write_kb(tmp: Path, concepts, actions, bugs):
    (tmp / "concepts.yaml").write_text(
        yaml.safe_dump({"groups": [{"id": "g", "name": "G"}], "concepts": concepts})
    )
    (tmp / "pedagogical_actions.yaml").write_text(yaml.safe_dump({"actions": actions}))
    (tmp / "bug_patterns.yaml").write_text(yaml.safe_dump({"bug_patterns": bugs}))
    (tmp / "problems").mkdir()
    return KnowledgeBase.load(tmp, tmp / "problems")


def test_validation_catches_cycles_and_broken_references(tmp_path):
    concepts = [
        {"id": "a", "name": "A", "group": "g", "prerequisites": ["b"]},
        {"id": "b", "name": "B", "group": "g", "prerequisites": ["a"]},
        {"id": "c", "name": "C", "group": "nhom_khong_co", "prerequisites": ["khong_co"]},
    ]
    actions = [
        {"id": "X", "type": "SAI_LOAI", "title": "x", "teaches": ["a"], "remediates": ["BUG_LA"],
         "styles": ["kinesthetic"], "problem": "P999"},
    ]  # fmt: skip
    bugs = [{"code": "B1", "name": "b", "concepts": ["khong_co"], "detected_by": []}]
    errors = "\n".join(_write_kb(tmp_path, concepts, actions, bugs).validate().errors)
    for expected in [
        "chu trình",
        "nhóm 'nhom_khong_co'",
        "concept tiên quyết 'khong_co'",
        "type 'SAI_LOAI'",
        "style 'kinesthetic'",
        "bug pattern 'BUG_LA'",
        "bài tập 'P999'",
        "bug B1: chưa có hành động",
    ]:
        assert expected in errors, expected
