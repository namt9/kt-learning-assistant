"""Chạy thật toàn bộ luồng chấm của hệ v0 (LocalRunner) trên chương trình mẫu có lỗi."""

import pytest

from backend.app.config import ROOT
from backend.app.schemas import Language, Submission, Verdict

from .conftest import FIXTURES


def run(judge, problems, problem_id, source, lang=Language.C):
    sub = Submission(student_id="sv1", problem_id=problem_id, language=lang, source_code=source)
    return judge.evaluate(sub, problems.get(problem_id))


def patterns(report):
    return {f.bug_pattern for f in report.findings}


@pytest.mark.parametrize("problem_dir", sorted((ROOT / "data" / "problems").glob("P*")))
def test_reference_solutions_are_accepted(judge, problems, problem_dir):
    pid = problem_dir.name.split("_")[0]
    rep = run(judge, problems, pid, (problem_dir / "solution.c").read_text())
    assert rep.grading.verdict == Verdict.AC, rep
    assert rep.grading.score == 100
    serious = patterns(rep) - {"UNUSED_VAR", "UNCLASSIFIED"}
    assert not serious, rep.findings


def test_cpp_submission(judge, problems):
    src = (
        "#include <iostream>\nint main(){ long long s=0; int n,x; std::cin>>n;"
        " while(n--){std::cin>>x; s+=x;} std::cout<<s<<'\\n'; }"
    )
    assert run(judge, problems, "P001", src, Language.CPP).grading.verdict == Verdict.AC


CASES = [
    # fixture, bài, verdict mong đợi (None = không kiểm tra), bug pattern bắt buộc có
    ("syntax.c", "P001", Verdict.CE, {"SYNTAX_ERROR", "UNDECLARED_ID"}),
    ("missing_amp.c", "P001", None, {"SCANF_MISSING_AMP"}),
    ("uninit.c", "P001", None, {"UNINIT_VAR"}),
    ("assign_cond.c", "P001", Verdict.WA, {"ASSIGN_IN_COND"}),
    ("stray_semicolon.c", "P001", Verdict.WA, {"STRAY_SEMICOLON"}),
    ("overflow.c", "P001", Verdict.WA, {"INT_OVERFLOW"}),
    ("infinite.c", "P001", Verdict.TLE, {"INFINITE_LOOP"}),
    ("leak.c", "P002", Verdict.AC, {"MEM_LEAK"}),
    ("heap_oob.c", "P002", None, {"ARRAY_OOB", "OFF_BY_ONE"}),
    ("int_div.c", "P003", Verdict.WA, {"INT_DIVISION"}),
]


@pytest.mark.parametrize(("fixture", "pid", "verdict", "expected"), CASES)
def test_buggy_programs(judge, problems, catalog, fixture, pid, verdict, expected):
    rep = run(judge, problems, pid, (FIXTURES / fixture).read_text())
    if verdict is not None:
        assert rep.grading.verdict == verdict, rep.grading
    assert expected <= patterns(rep), rep.findings
    assert all(f.hint for f in rep.findings)  # mọi lỗi đều có gợi ý từ danh mục


def test_no_unclassified_from_tools_on_fixtures(judge, problems):
    """Mọi cảnh báo công cụ trên bộ chương trình mẫu phải được phân loại vào một Bug Pattern."""
    leftovers = []
    for fixture, pid, _, _ in CASES:
        rep = run(judge, problems, pid, (FIXTURES / fixture).read_text())
        leftovers += [(fixture, f.message) for f in rep.findings if f.bug_pattern == "UNCLASSIFIED"]
    assert not leftovers, leftovers
