"""Diagnosis Agent và lớp trung gian LLM, dùng LLM/KG giả (không tốn phí, không cần mạng)."""

from dataclasses import dataclass
from datetime import datetime

import pytest

from backend.app.agents.diagnosis import DiagnosisAgent
from backend.app.llm import FallbackLLM, LLMError
from backend.app.schemas import (
    DiagnosisMode,
    Finding,
    GradingResult,
    Language,
    SubmissionReport,
    Verdict,
)

SOURCE = "int main(void) {\n    int sum;\n    sum += 1;\n    return sum;\n}\n"


class FakeLLM:
    """Provider giả: ghi lại yêu cầu và trả về dữ liệu cho trước (hoặc ném lỗi)."""

    def __init__(self, name="fake", reply=None, error=None):
        self.name, self.reply, self.error = name, reply, error
        self.calls = []

    def generate_json(self, system, user, schema):
        self.calls.append({"system": system, "user": user, "schema": schema})
        if self.error:
            raise LLMError(self.error)
        return self.reply


@dataclass
class Action:
    id: str
    title: str
    content: str


class FakeKG:
    def concepts_for_bugs(self, codes):
        return [{"id": "khoi_tao", "name": "Khởi tạo biến"}]

    def remediation(self, code, styles=None, limit=3):
        return [Action(f"PA_{code}", f"Sửa {code}", "nội dung")]


def report(findings, verdict=Verdict.WA):
    return SubmissionReport(
        submission_id="s1",
        student_id="sv",
        problem_id="P001",
        language=Language.C,
        created_at=datetime.fromisoformat("2026-11-17T08:00:00+00:00"),
        grading=GradingResult(submission_id="s1", verdict=verdict, score=0, total=3),
        findings=findings,
    )


UNINIT = [
    Finding(bug_pattern="UNINIT_VAR", source="gcc", line=3, message="sum is used uninitialized"),
    Finding(bug_pattern="UNINIT_VAR", source="cppcheck", line=3, message="uninitvar"),
    Finding(bug_pattern="INT_OVERFLOW", source="ubsan", line=7, message="signed overflow"),
]


def agent(catalog, llm=None, kg=None):
    return DiagnosisAgent(catalog, kg or FakeKG(), FallbackLLM([llm]) if llm else None)


def test_rule_mode_groups_findings_and_uses_kg(catalog):
    d = agent(catalog).diagnose(report(UNINIT), SOURCE, mode=DiagnosisMode.RULE)
    assert d.mode == DiagnosisMode.RULE and d.llm_provider is None
    assert [it.bug_pattern for it in d.items] == ["UNINIT_VAR", "INT_OVERFLOW"]
    assert d.items[0].lines == [3]
    assert d.items[0].actions == ["PA_UNINIT_VAR"] and d.items[0].fix_hint == "Sửa UNINIT_VAR"
    assert "kg:PedagogicalAction:PA_UNINIT_VAR" in d.references
    assert "khoi_tao" in d.related_concepts


def test_hybrid_uses_llm_explanations_and_constrains_codes(catalog):
    llm = FakeLLM(reply={
        "summary": "Biến sum chưa khởi tạo.",
        "items": [{"bug_pattern": "UNINIT_VAR", "explanation": "Dòng 3 dùng sum khi chưa gán.",
                   "fix_hint": "Gán sum = 0 trước vòng lặp."}],
    })  # fmt: skip
    d = agent(catalog, llm).diagnose(report(UNINIT), SOURCE)
    assert d.mode == DiagnosisMode.HYBRID and d.llm_provider == "fake"
    assert d.explanation == "Biến sum chưa khởi tạo."
    assert d.items[0].explanation == "Dòng 3 dùng sum khi chưa gán."
    # lỗi LLM không giải thích vẫn giữ giải thích của luật
    assert d.items[1].explanation == catalog.get("INT_OVERFLOW").hint
    call = llm.calls[0]
    enum = call["schema"]["properties"]["items"]["items"]["properties"]["bug_pattern"]["enum"]
    assert enum == ["UNINIT_VAR", "INT_OVERFLOW"]  # LLM chỉ được chọn lỗi luật đã thấy
    assert "  3|     sum += 1;" in call["user"]  # code có đánh số dòng
    assert "Khởi tạo biến" in call["user"] and "PA_" not in call["user"]


def test_hybrid_rejects_hallucinated_codes(catalog):
    llm = FakeLLM(reply={"summary": "x", "items": [
        {"bug_pattern": "MEM_LEAK", "explanation": "bịa", "fix_hint": "bịa"}]})  # fmt: skip
    d = agent(catalog, llm).diagnose(report(UNINIT), SOURCE)
    assert d.rejected == ["MEM_LEAK"]
    assert {it.bug_pattern for it in d.items} == {"UNINIT_VAR", "INT_OVERFLOW"}
    assert all("bịa" not in it.explanation for it in d.items)


def test_hybrid_falls_back_to_rule_when_llm_fails(catalog):
    d = agent(catalog, FakeLLM(error="hết hạn mức")).diagnose(report(UNINIT), SOURCE)
    assert d.mode == DiagnosisMode.RULE
    assert any("hết hạn mức" in n for n in d.notes)
    no_llm = agent(catalog).diagnose(report(UNINIT), SOURCE)
    assert no_llm.mode == DiagnosisMode.RULE and no_llm.notes


def test_kg_unavailable_still_diagnoses(catalog):
    d = DiagnosisAgent(catalog, None, None).diagnose(report(UNINIT), SOURCE)
    assert d.items[0].concepts == list(catalog.get("UNINIT_VAR").concepts)
    assert d.items[0].actions == [] and d.items[0].fix_hint == ""
    assert any("KG" in n for n in d.notes)


def test_no_findings(catalog):
    ok = agent(catalog).diagnose(report([], Verdict.AC), SOURCE)
    assert ok.items == [] and "đạt" in ok.explanation


def test_llm_only_mode(catalog):
    llm = FakeLLM(reply={"summary": "s", "items": [
        {"bug_pattern": "UNINIT_VAR", "line": 3, "explanation": "e", "fix_hint": "f"},
        {"bug_pattern": "KHONG_CO", "line": 0, "explanation": "e", "fix_hint": "f"}]})  # fmt: skip
    d = agent(catalog, llm).diagnose(report(UNINIT), SOURCE, mode=DiagnosisMode.LLM_ONLY)
    assert [(f.bug_pattern, f.source, f.line) for f in d.findings] == [("UNINIT_VAR", "llm", 3)]
    assert d.rejected == ["KHONG_CO"]
    # cấu hình đối chứng: LLM không được thấy kết quả của luật
    assert "uninitvar" not in llm.calls[0]["user"]
    with pytest.raises(LLMError):
        agent(catalog).diagnose(report(UNINIT), SOURCE, mode=DiagnosisMode.LLM_ONLY)


def test_fallback_chain_uses_next_provider():
    chain = FallbackLLM([FakeLLM("claude", error="mất mạng"), FakeLLM("ollama", reply={"ok": 1})])
    res = chain.generate("s", "u", {})
    assert res.provider == "ollama" and res.data == {"ok": 1}
    assert res.attempts == ["claude: mất mạng"]
    with pytest.raises(LLMError, match="a: x; b: y"):
        FallbackLLM([FakeLLM("a", error="x"), FakeLLM("b", error="y")]).generate("s", "u", {})


def test_diagnosis_api_and_cache(client):
    src = '#include <stdio.h>\nint main(void){int n; scanf("%d", n); return 0;}'
    sid = client.post("/submit", json={"student_id": "sv", "problem_id": "P001",
                                       "source_code": src}).json()["submission_id"]  # fmt: skip
    llm = FakeLLM(reply={"summary": "Thiếu &.", "items": []})
    client.app.state.llm = FallbackLLM([llm])
    client.app.state.kg = FakeKG()

    d = client.post(f"/submissions/{sid}/diagnosis").json()
    assert d["mode"] == "hybrid" and d["explanation"] == "Thiếu &."
    assert "SCANF_MISSING_AMP" in {it["bug_pattern"] for it in d["items"]}
    client.post(f"/submissions/{sid}/diagnosis")
    assert len(llm.calls) == 1  # lần hai lấy từ cache, không gọi LLM
    client.post(f"/submissions/{sid}/diagnosis?refresh=true")
    assert len(llm.calls) == 2

    rule = client.post(f"/submissions/{sid}/diagnosis?mode=rule").json()
    assert rule["mode"] == "rule" and rule["llm_provider"] is None
    assert client.post("/submissions/khong-co/diagnosis").status_code == 404

    client.app.state.llm = None
    assert client.post(f"/submissions/{sid}/diagnosis?mode=llm_only").status_code == 503
    client.app.state.kg = None  # KG giả không có driver để đóng khi tắt app


def test_suppressed_findings_are_not_explained(catalog):
    findings = [
        Finding(bug_pattern="SCANF_MISSING_AMP", source="custom_rule", line=4, message="thiếu &"),
        Finding(bug_pattern="NULL_DEREF", source="asan", line=4, message="SEGV",
                suppressed_by="MR009"),
    ]  # fmt: skip
    d = agent(catalog).diagnose(report(findings), SOURCE, mode=DiagnosisMode.RULE)
    assert [it.bug_pattern for it in d.items] == ["SCANF_MISSING_AMP"]
    assert any("NULL_DEREF" in n and "MR009" in n for n in d.notes)
