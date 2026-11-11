"""Hệ v0: biên dịch -> phân tích tĩnh -> chạy test -> chạy lại với sanitizer -> gộp lỗi."""

from __future__ import annotations

import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..problems import ProblemData
from ..rules.catalog import Catalog
from ..rules.custom import run_custom_rules
from ..rules.engine import merge_findings
from ..rules.tools import CPPCHECK_TEMPLATE, parse_cppcheck, parse_gcc, parse_sanitizer
from ..schemas import (
    Finding,
    GradingResult,
    Language,
    Submission,
    SubmissionReport,
    TestResult,
    Verdict,
)
from .runner import Runner

_COMPILERS = {
    Language.C: ["gcc", "-std=c11"],
    Language.CPP: ["g++", "-std=c++17"],
}
_WARN = ["-Wall", "-Wextra", "-Wno-unused-parameter"]
_SANITIZE = ["-g", "-O0", "-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
_SAN_ENV = (
    "ASAN_OPTIONS=detect_leaks=1:abort_on_error=0:exitcode=86 "
    "UBSAN_OPTIONS=print_stacktrace=1:halt_on_error=0"
)
_MAX_SAN_TESTS = 3  # số test chạy lại với sanitizer (tốn thời gian)


def normalize_output(s: str) -> list[str]:
    lines = [ln.rstrip() for ln in s.replace("\r\n", "\n").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return lines


class Judge:
    def __init__(self, runner: Runner, catalog: Catalog, work_root: Path, compile_timeout_s=20.0):
        self.runner = runner
        self.catalog = catalog
        self.work_root = work_root
        self.compile_timeout_s = compile_timeout_s

    def evaluate(self, sub: Submission, problem: ProblemData) -> SubmissionReport:
        sid = uuid.uuid4().hex[:12]
        self.work_root.mkdir(parents=True, exist_ok=True)
        workdir = Path(tempfile.mkdtemp(prefix=f"sub_{sid}_", dir=self.work_root))
        workdir.chmod(0o777)  # user "runner" trong container cần ghi file biên dịch
        try:
            return self._evaluate(sid, workdir, sub, problem)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    # ------------------------------------------------------------------

    def _evaluate(self, sid, workdir: Path, sub: Submission, problem: ProblemData):
        tools = self.runner.available_tools()
        unavailable = sorted({"cppcheck"} - tools)
        src_name = "main.c" if sub.language == Language.C else "main.cpp"
        (workdir / src_name).write_text(sub.source_code, encoding="utf-8")
        compiler = _COMPILERS[sub.language]

        findings: list[Finding] = []
        comp = self.runner.run(
            [*compiler, "-O2", *_WARN, src_name, "-o", "main", "-lm"],
            workdir,
            timeout_s=self.compile_timeout_s,
            memory_mb=None,
        )
        compile_output = (comp.stderr + comp.stdout).strip() or None
        findings += parse_gcc(compile_output or "")
        findings += run_custom_rules(sub.source_code)
        if "cppcheck" in tools:
            findings += self._cppcheck(workdir, src_name, sub.language)

        total = len(problem.tests)
        if comp.exit_code != 0:
            grading = GradingResult(
                submission_id=sid,
                verdict=Verdict.CE,
                score=0,
                total=total,
                compile_output=compile_output,
            )
            return self._report(sid, sub, grading, findings, unavailable)

        tests = self._run_tests(workdir, problem)
        passed = sum(t.verdict == Verdict.AC for t in tests)
        verdict = next((t.verdict for t in tests if t.verdict != Verdict.AC), Verdict.AC)
        if verdict == Verdict.TLE:
            findings.append(
                Finding(
                    bug_pattern="INFINITE_LOOP",
                    source="judge",
                    message="Chương trình chạy quá giới hạn thời gian ở ít nhất một test",
                    confidence=0.7,
                )
            )
        findings += self._sanitize(workdir, src_name, compiler, problem, tests)

        grading = GradingResult(
            submission_id=sid,
            verdict=verdict,
            score=round(100 * passed / total, 2) if total else 0,
            passed=passed,
            total=total,
            compile_output=compile_output,
            tests=tests,
        )
        return self._report(sid, sub, grading, findings, unavailable)

    def _report(self, sid, sub, grading, findings, unavailable) -> SubmissionReport:
        return SubmissionReport(
            submission_id=sid,
            student_id=sub.student_id,
            problem_id=sub.problem_id,
            language=sub.language,
            created_at=datetime.now(timezone.utc),
            grading=grading,
            findings=merge_findings(findings, self.catalog),
            tools_unavailable=unavailable,
        )

    def _cppcheck(self, workdir: Path, src_name: str, lang: Language) -> list[Finding]:
        r = self.runner.run(
            [
                "cppcheck",
                "--enable=warning,style,performance,portability",
                "--inline-suppr",
                f"--language={'c' if lang == Language.C else 'c++'}",
                f"--template={CPPCHECK_TEMPLATE}",
                "--quiet",
                src_name,
            ],
            workdir,
            timeout_s=self.compile_timeout_s,
            memory_mb=None,
        )
        return parse_cppcheck(r.stderr + r.stdout)

    def _run_tests(self, workdir: Path, problem: ProblemData) -> list[TestResult]:
        meta = problem.meta
        results = []
        for idx, tc in enumerate(problem.tests):
            r = self.runner.run(
                ["./main"], workdir, stdin=tc.input, timeout_s=meta.time_limit_s,
                memory_mb=meta.memory_mb,
            )  # fmt: skip
            if r.timed_out:
                v = Verdict.TLE
            elif r.oom_killed:
                v = Verdict.MLE
            elif r.exit_code != 0:
                v = Verdict.RE
            elif normalize_output(r.stdout) == normalize_output(tc.expected):
                v = Verdict.AC
            else:
                v = Verdict.WA
            sample = idx == 0  # chỉ lộ chi tiết test đầu tiên (test mẫu)
            results.append(
                TestResult(
                    test_id=tc.id,
                    verdict=v,
                    time_ms=r.time_ms,
                    input=tc.input if sample else None,
                    expected=tc.expected if sample else None,
                    stdout=r.stdout[:2000] if sample else None,
                    stderr=r.stderr[:2000] if (sample or v == Verdict.RE) else None,
                )
            )
        return results

    def _sanitize(self, workdir, src_name, compiler, problem: ProblemData, tests):
        """Biên dịch lại với ASan/UBSan, chạy trên test lỗi trước rồi tới test mẫu."""
        build = self.runner.run(
            [*compiler, *_SANITIZE, src_name, "-o", "main_san", "-lm"],
            workdir,
            timeout_s=self.compile_timeout_s,
            memory_mb=None,
        )
        if build.exit_code != 0:
            return []
        order = sorted(range(len(tests)), key=lambda i: tests[i].verdict == Verdict.AC)
        findings: list[Finding] = []
        for i in order[:_MAX_SAN_TESTS]:
            r = self.runner.run(
                ["sh", "-c", f"{_SAN_ENV} ./main_san"],
                workdir,
                stdin=problem.tests[i].input,
                timeout_s=max(problem.meta.time_limit_s * 5, 3),
                memory_mb=None,
            )
            findings += parse_sanitizer(r.stderr)
        return findings
