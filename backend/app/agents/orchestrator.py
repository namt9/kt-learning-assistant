"""Orchestrator: điều phối các agent cho một lần nộp bài.

    Grading Agent (judge v0)
      -> luật khai phá khử cảnh báo hệ quả
      -> lưu log (SQLite) + cập nhật Knowledge Graph
      -> Diagnosis Agent (luật + KG + LLM)
      -> Learning-Path Agent (KG, dự phòng bằng tri thức YAML)

Mỗi bước ghi vào `trace` (agent, trạng thái, thời gian) để giao diện hiển thị luồng multi-agent.
Bước nào lỗi thì ghi lại và chạy tiếp: sinh viên luôn nhận được ít nhất kết quả chấm.

Luồng cố định nên viết thẳng bằng Python thay vì dùng LangGraph: dễ đọc, dễ test, không thêm
phụ thuộc. Phần hội thoại (chọn agent theo câu hỏi) sẽ dựa trên lớp này.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import contextmanager

from ..judge.judge import Judge
from ..kg.model import KnowledgeBase
from ..llm import FallbackLLM, LLMError
from ..problems import ProblemRepository
from ..rules.catalog import Catalog
from ..rules.mined import MinedRules
from ..schemas import (
    AgentStep,
    Diagnosis,
    DiagnosisMode,
    StudentProfile,
    Submission,
    TutorResponse,
)
from ..storage import Storage
from ..student.profile import build_profile
from .diagnosis import DiagnosisAgent
from .learning_path import LearningPathAgent


class SubmissionNotFound(KeyError):
    pass


class Tutor:
    def __init__(
        self,
        *,
        judge: Judge,
        problems: ProblemRepository,
        storage: Storage,
        catalog: Catalog,
        kb: KnowledgeBase,
        mined: MinedRules,
        kg: Callable[[], object | None],
        llm: Callable[[], FallbackLLM | None],
    ):
        self.judge, self.problems, self.storage = judge, problems, storage
        self.catalog, self.kb, self.mined = catalog, kb, mined
        self._kg, self._llm = kg, llm

    # ------------------------------------------------------------ tiện ích

    @staticmethod
    @contextmanager
    def _step(trace: list[AgentStep], agent: str):
        rec = AgentStep(agent=agent, status="ok", ms=0)
        t = time.perf_counter()
        try:
            yield rec
        except Exception as e:  # một agent lỗi không được làm hỏng cả lượt
            rec.status, rec.detail = "error", f"{type(e).__name__}: {e}"
        finally:
            rec.ms = int((time.perf_counter() - t) * 1000)
            trace.append(rec)

    def style_detail(self, student_id: str):
        """Phong cách học từng chiều: bảng hỏi kết hợp hành vi tương tác."""
        from ..student.learning_style import estimate

        return estimate(self.storage.get_style_answers(student_id),
                        self.storage.timeline(student_id), self.kb)  # fmt: skip

    def styles(self, student_id: str) -> list[str]:
        from ..student.learning_style import effective_styles

        return effective_styles(self.style_detail(student_id)) or []

    def _history_bugs(self, student_id: str, exclude: str | None = None) -> set[str]:
        return {
            f.bug_pattern
            for r in self.storage.reports(student_id)
            if r.submission_id != exclude
            for f in r.findings
            if not f.suppressed_by
        }

    # ------------------------------------------------------------ chẩn đoán

    def diagnose(
        self,
        submission_id: str,
        mode: DiagnosisMode = DiagnosisMode.HYBRID,
        styles: list[str] | None = None,
        refresh: bool = False,
    ) -> Diagnosis:
        """Chẩn đoán một lần nộp đã lưu; có cache để không gọi LLM lặp lại (tốn phí)."""
        report = self.storage.get(submission_id)
        if report is None:
            raise SubmissionNotFound(submission_id)
        styles = self.styles(report.student_id) if styles is None else styles
        if not refresh and (
            cached := self.storage.get_diagnosis(submission_id, mode.value, styles)
        ):
            return cached
        try:
            problem = self.problems.get(report.problem_id)
        except KeyError:
            problem = None
        agent = DiagnosisAgent(self.catalog, self._kg(), self._llm())
        d = agent.diagnose(report, self.storage.get_source(submission_id), problem, mode, styles)
        if d.mode == mode:  # kết quả đã phải lùi về luật thì không lưu, để lần sau thử LLM lại
            self.storage.save_diagnosis(d, mode.value, styles)
        payload = {"submission_id": submission_id, "mode": d.mode.value}
        self.storage.log_interaction(report.student_id, "diagnosis", payload)
        return d

    # ------------------------------------------------------------ một lượt nộp bài

    def submit(self, sub: Submission, mode: DiagnosisMode = DiagnosisMode.HYBRID) -> TutorResponse:
        trace: list[AgentStep] = []
        problem = self.problems.get(sub.problem_id)  # ProblemNotFound -> 404 ở tầng API

        with self._step(trace, "grading") as st:
            report = self.judge.evaluate(sub, problem)
            st.detail = f"{report.grading.verdict.value}, {len(report.findings)} cảnh báo"
        if trace[-1].status == "error":
            raise RuntimeError(trace[-1].detail)  # không chấm được thì không có gì để làm tiếp

        with self._step(trace, "mined_rules") as st:
            report.findings = self.mined.apply(report, sub.source_code)
            hidden = [f.bug_pattern for f in report.findings if f.suppressed_by]
            st.detail = f"khử {len(hidden)} cảnh báo hệ quả" + (
                f": {', '.join(hidden)}" if hidden else ""
            )

        self.storage.save(report, sub.source_code)
        primary = list(dict.fromkeys(f.bug_pattern for f in report.findings if not f.suppressed_by))
        self.storage.log_interaction(sub.student_id, "submit", {
            "submission_id": report.submission_id, "problem_id": sub.problem_id,
            "verdict": report.grading.verdict.value, "bugs": primary,
        })  # fmt: skip

        kg = self._kg()
        with self._step(trace, "knowledge_graph") as st:
            if kg is None:
                st.status, st.detail = "skipped", "Neo4j không chạy"
            else:
                from ..kg.loader import upsert_submission

                with kg.driver.session(database=kg.database) as s:
                    upsert_submission(s, report)
                st.detail = "đã thêm StudentCode và quan hệ EXHIBITS"

        styles = self.styles(sub.student_id)
        diagnosis = None
        with self._step(trace, "diagnosis") as st:
            try:
                diagnosis = self.diagnose(report.submission_id, mode, styles)
            except LLMError as e:
                st.status, st.detail = "error", f"LLM không khả dụng: {e}"
            else:
                if diagnosis.mode != mode:
                    st.status = "fallback"
                st.detail = f"{diagnosis.mode.value}" + (
                    f" qua {diagnosis.llm_provider}" if diagnosis.llm_provider else ""
                )

        path = None
        with self._step(trace, "learning_path") as st:
            if not primary:
                st.status, st.detail = "skipped", "không có lỗi cần ôn"
            else:
                agent = LearningPathAgent(self.kb, kg)
                history = self._history_bugs(sub.student_id, exclude=report.submission_id)
                path, note = agent.plan(sub.student_id, primary, styles, history)
                if note:
                    st.status, st.detail = "fallback", note
                else:
                    st.detail = f"{len(path.steps)} bước (Neo4j)"

        return TutorResponse(report=report, diagnosis=diagnosis, learning_path=path, trace=trace)

    # ------------------------------------------------------------ hồ sơ

    def profile(self, student_id: str) -> StudentProfile:
        from ..student.learning_style import effective_styles

        detail = self.style_detail(student_id)
        return build_profile(student_id, self.storage.reports(student_id), self.kb,
                             effective_styles(detail), detail)  # fmt: skip
