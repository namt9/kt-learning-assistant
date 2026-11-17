"""Hợp đồng dữ liệu dùng chung giữa các module/agent.

BẢN NHÁP: cả nhóm chốt trong tuần 1. Mọi thay đổi phải qua PR và cần 2 người duyệt,
vì các module khác (và mock của họ) phụ thuộc vào file này.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Language(str, Enum):
    C = "c"
    CPP = "cpp"


class Verdict(str, Enum):
    AC = "AC"  # Accepted
    WA = "WA"  # Wrong Answer
    CE = "CE"  # Compile Error
    RE = "RE"  # Runtime Error
    TLE = "TLE"  # Time Limit Exceeded
    MLE = "MLE"  # Memory Limit Exceeded


# ---------------------------------------------------------------- Bài tập


class ProblemSummary(BaseModel):
    id: str
    title: str
    concepts: list[str] = []


class Problem(ProblemSummary):
    statement: str
    languages: list[Language] = [Language.C, Language.CPP]
    time_limit_s: float = 1.0
    memory_mb: int = 64
    test_count: int = 0


# ---------------------------------------------------------------- Nộp bài & chấm


class Submission(BaseModel):
    student_id: str = Field(min_length=1, max_length=64)
    problem_id: str
    language: Language = Language.C
    source_code: str = Field(min_length=1, max_length=64_000)


class TestResult(BaseModel):
    test_id: str
    verdict: Verdict
    time_ms: int | None = None
    # Chỉ điền cho test mẫu (test đầu tiên) để sinh viên tự đối chiếu; các test khác ẩn.
    input: str | None = None
    expected: str | None = None
    stdout: str | None = None
    stderr: str | None = None


class GradingResult(BaseModel):
    """Đầu ra của module chấm / Grading Agent."""

    submission_id: str
    verdict: Verdict
    score: float = Field(ge=0, le=100)
    passed: int = 0
    total: int = 0
    compile_output: str | None = None
    tests: list[TestResult] = []


class Finding(BaseModel):
    """Một lỗi do rule engine phát hiện, đã ánh xạ sang mã Bug Pattern trong KG."""

    bug_pattern: str  # mã trong knowledge/bug_patterns.yaml, ví dụ "MEM_LEAK"
    source: str  # "gcc" | "cppcheck" | "asan" | "ubsan" | "custom_rule" | "judge" | "mined_rule"
    line: int | None = None
    message: str
    confidence: float = Field(default=1.0, ge=0, le=1)
    hint: str | None = None  # gợi ý cố định (v0); v1 thay bằng giải thích của Diagnosis Agent


class SubmissionReport(BaseModel):
    """Kết quả đầy đủ của hệ v0 cho một lần nộp: chấm điểm + lỗi phát hiện bằng luật."""

    submission_id: str
    student_id: str
    problem_id: str
    language: Language
    created_at: datetime
    grading: GradingResult
    findings: list[Finding] = []
    tools_unavailable: list[str] = []  # công cụ phân tích không có trên máy chấm


# ---------------------------------------------------------------- v1 (Multi-Agent)


class Diagnosis(BaseModel):
    """Đầu ra của Diagnosis Agent (hybrid: luật xác định lỗi, LLM giải thích)."""

    submission_id: str
    findings: list[Finding]
    related_concepts: list[str] = []  # id concept trong KG
    explanation: str  # giải thích bằng ngôn ngữ tự nhiên
    references: list[str] = []  # nguồn RAG đã dùng


class LearningStep(BaseModel):
    concept: str
    action: str  # Pedagogical_Action, ví dụ "xem ví dụ", "làm bài tập P007"
    resource: str | None = None


class LearningPath(BaseModel):
    """Đầu ra của Learning-Path Agent."""

    student_id: str
    steps: list[LearningStep]
