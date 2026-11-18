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
    # "gcc" | "cppcheck" | "asan" | "ubsan" | "custom_rule" | "judge" | "mined_rule" | "llm"
    source: str
    line: int | None = None
    message: str
    confidence: float = Field(default=1.0, ge=0, le=1)
    hint: str | None = None  # gợi ý cố định (v0); v1 thay bằng giải thích của Diagnosis Agent
    # v1: id luật khai phá cho biết cảnh báo chỉ là hệ quả của lỗi gốc khác (giữ lại để truy vết)
    suppressed_by: str | None = None


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


class DiagnosisMode(str, Enum):
    RULE = "rule"  # chỉ luật + KG, không gọi LLM
    LLM_ONLY = "llm_only"  # LLM tự tìm lỗi từ code (cấu hình đối chứng)
    HYBRID = "hybrid"  # luật xác định lỗi, KG cấp tri thức, LLM chỉ giải thích


class DiagnosisItem(BaseModel):
    """Giải thích cho một mã lỗi (gộp mọi dòng mắc cùng mã)."""

    bug_pattern: str
    lines: list[int] = []
    explanation: str
    fix_hint: str
    concepts: list[str] = []  # id concept trong KG
    actions: list[str] = []  # id PedagogicalAction gợi ý học thêm


class Diagnosis(BaseModel):
    """Đầu ra của Diagnosis Agent (hybrid: luật xác định lỗi, LLM giải thích)."""

    submission_id: str
    findings: list[Finding]
    related_concepts: list[str] = []  # id concept trong KG
    explanation: str  # giải thích bằng ngôn ngữ tự nhiên
    references: list[str] = []  # nguồn tri thức đã dùng (node KG, ...)
    items: list[DiagnosisItem] = []
    mode: DiagnosisMode = DiagnosisMode.HYBRID
    llm_provider: str | None = None  # provider đã trả lời; None nếu không dùng LLM
    rejected: list[str] = []  # mã lỗi LLM đưa ra nhưng luật không phát hiện, đã loại
    notes: list[str] = []  # cảnh báo vận hành (LLM lỗi, KG tắt, ...)


class LearningStep(BaseModel):
    concept: str
    action: str  # tiêu đề Pedagogical_Action, ví dụ "Chỉ số mảng từ 0 đến n-1"
    action_id: str | None = None  # id node PedagogicalAction trong KG
    action_type: str | None = None  # GIAI_THICH | VI_DU | TRUC_QUAN | GO_LOI | BAI_TAP | CAU_HOI
    resource: str | None = None  # id bài tập (Problem) nếu hành động là luyện tập
    reason: str | None = None  # vì sao bước này có trong lộ trình


class LearningPath(BaseModel):
    """Đầu ra của Learning-Path Agent."""

    student_id: str
    steps: list[LearningStep]
    source: str = "kg"  # "kg": suy luận trên Neo4j | "offline": cùng thuật toán trên tri thức YAML


# ---------------------------------------------------------------- Hồ sơ sinh viên (v1)


class ConceptMastery(BaseModel):
    concept: str
    name: str
    group: str
    mastery: float = Field(ge=0, le=1)  # ước lượng mức thành thạo, 0.5 = chưa đủ dữ liệu
    evidence: float  # tổng trọng số bằng chứng (lần nộp gần đây nặng hơn)
    successes: float
    errors: float


class GroupMastery(BaseModel):
    group: str
    name: str
    mastery: float | None  # None: chưa có bằng chứng nào trong nhóm
    concepts: int


class StudentProfile(BaseModel):
    student_id: str
    styles: list[str] | None  # None: chưa làm bảng hỏi phong cách học
    submissions: int
    accepted: int
    concepts: list[ConceptMastery]
    groups: list[GroupMastery]
    top_bugs: list[dict]  # [{"bug": mã, "name": tên, "times": số lần}]


# ---------------------------------------------------------------- Orchestrator (v1)


class AgentStep(BaseModel):
    """Một bước trong luồng của Orchestrator, để giao diện và báo cáo thấy agent nào đã chạy."""

    agent: str  # grading | mined_rules | diagnosis | learning_path | profile
    status: str  # ok | fallback | skipped | error
    ms: int
    detail: str = ""


class TutorResponse(BaseModel):
    report: SubmissionReport
    diagnosis: Diagnosis | None = None
    learning_path: LearningPath | None = None
    trace: list[AgentStep] = []
