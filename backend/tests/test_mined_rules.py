"""Áp luật khử nhiễu đã khai phá lên kết quả tầng luật."""

from datetime import datetime

from backend.app.config import ROOT
from backend.app.rules.mined import MinedRules
from backend.app.schemas import Finding, GradingResult, Language, SubmissionReport, Verdict

RULES = [
    {"id": "MR1", "kind": "suppress", "if": ["found=NULL_DEREF", "found=SCANF_MISSING_AMP"],
     "then": "NULL_DEREF", "confidence": 1.0},
    {"id": "MR2", "kind": "suppress", "if": ["found=ARRAY_OOB", "verdict=RE"],
     "then": "ARRAY_OOB", "confidence": 0.93},
    {"id": "MR3", "kind": "add", "if": ["verdict=TLE"], "then": "INFINITE_LOOP", "confidence": 1.0},
    {"id": "MR4", "kind": "suppress", "if": ["found=UNINIT_VAR"], "then": "UNINIT_VAR",
     "confidence": 0.7},
]  # fmt: skip


def rep(verdict, codes):
    return SubmissionReport(
        submission_id="s", student_id="sv", problem_id="P001", language=Language.C,
        created_at=datetime.fromisoformat("2026-11-18T08:00:00+00:00"),
        grading=GradingResult(submission_id="s", verdict=verdict, score=0),
        findings=[Finding(bug_pattern=c, source="asan", line=i, message=c)
                  for i, c in enumerate(codes, 1)],
    )  # fmt: skip


def test_only_confident_suppress_rules_are_used():
    rules = MinedRules(RULES)
    assert [r["id"] for r in rules.rules] == ["MR1", "MR2"]  # MR3 là luật bổ sung, MR4 conf thấp


def test_cascading_warning_is_marked_not_removed():
    out = MinedRules(RULES).apply(rep(Verdict.RE, ["SCANF_MISSING_AMP", "NULL_DEREF"]), "")
    assert [(f.bug_pattern, f.suppressed_by) for f in out] == [
        ("SCANF_MISSING_AMP", None), ("NULL_DEREF", "MR1")]  # fmt: skip


def test_never_suppresses_every_finding():
    out = MinedRules(RULES).apply(rep(Verdict.RE, ["ARRAY_OOB"]), "")
    assert out[0].suppressed_by is None  # khử hết thì không còn lỗi gốc nào để giải thích


def test_repository_rules_file_loads():
    rules = MinedRules.load(ROOT / "knowledge" / "mined_rules.yaml")
    assert len(rules) > 0 and all(r["kind"] == "suppress" for r in rules.rules)
    assert len(MinedRules.load(ROOT / "khong_co.yaml")) == 0
