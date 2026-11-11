"""Hợp đồng dữ liệu dùng chung giữa các module/agent.

BẢN NHÁP: cả nhóm chốt trong tuần 1. Mọi thay đổi phải qua PR và cần 2 người duyệt,
vì các module khác (và mock của họ) phụ thuộc vào file này.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    AC = "AC"  # Accepted
    WA = "WA"  # Wrong Answer
    CE = "CE"  # Compile Error
    RE = "RE"  # Runtime Error
    TLE = "TLE"  # Time Limit Exceeded
    MLE = "MLE"  # Memory Limit Exceeded


class Submission(BaseModel):
    student_id: str
    problem_id: str
    language: str = "c"  # "c" | "cpp"
    source_code: str


class TestResult(BaseModel):
    test_id: str
    verdict: Verdict
    time_ms: int | None = None
    stdout: str | None = None
    stderr: str | None = None


class GradingResult(BaseModel):
    """Đầu ra của module chấm / Grading Agent."""

    submission_id: str
    verdict: Verdict
    score: float = Field(ge=0, le=100)
    compile_output: str | None = None
    tests: list[TestResult] = []


class Finding(BaseModel):
    """Một lỗi do rule engine phát hiện, đã ánh xạ sang mã Bug Pattern trong KG."""

    bug_pattern: str  # mã trong knowledge/bug_patterns.yaml, ví dụ "MEM_LEAK"
    source: str  # "gcc" | "cppcheck" | "asan" | "custom_rule" | "mined_rule"
    line: int | None = None
    message: str
    confidence: float = Field(default=1.0, ge=0, le=1)


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
