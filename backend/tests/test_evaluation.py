"""Script so sánh 3 cấu hình chẩn đoán, chạy với LLM giả."""

import json

import pytest

from backend.app.evaluation import compare
from backend.app.llm import FallbackLLM

REC = {
    "id": "r1",
    "problem_id": "P001",
    "concepts": ["mang"],
    "labels": ["SCANF_MISSING_AMP"],
    "ops": ["drop_amp@5"],
    "verdict": "RE",
    "score": 0,
    "findings": [
        {"bug_pattern": "NULL_DEREF", "source": "asan", "line": 5},
        {"bug_pattern": "SCANF_MISSING_AMP", "source": "custom_rule", "line": 5},
        {"bug_pattern": "UNINIT_VAR", "source": "gcc", "line": 5},
    ],
    "source": "#include <stdio.h>\nint main(void) {\n    int n;\n    long long s = 0;\n"
    '    scanf("%d", n);\n    return 0;\n}\n',
}
REC2 = {
    **REC,
    "id": "r2",
    "labels": ["OFF_BY_ONE"],
    "ops": ["lt_to_le@7"],
    "verdict": "WA",
    "findings": [],
}


class FakeLLM:
    name = "fake"

    def __init__(self):
        self.calls = 0

    def generate_json(self, system, user, schema):
        self.calls += 1
        props = schema["properties"]
        if "extra" in props or "line" not in props["items"]["items"]["properties"]:  # hybrid
            enum = props.get("items", {}).get("items", {}).get("properties", {})
            verified = enum.get("bug_pattern", {}).get("enum", [])
            reply = {"summary": "s", "items": [], "extra": []}
            if verified:
                reply["items"] = [
                    {"bug_pattern": verified[0], "explanation": "Dòng 5 thiếu &.", "fix_hint": "&"}
                ]
            if "extra" in props and not verified:  # công cụ không thấy gì: LLM đề xuất
                reply["extra"] = [
                    {"bug_pattern": "OFF_BY_ONE", "line": 7, "explanation": "e", "fix_hint": "f"},
                    {"bug_pattern": "MEM_LEAK", "line": 0, "explanation": "bịa", "fix_hint": "x"},
                ]
            return reply
        return {  # llm_only
            "summary": "s",
            "items": [
                {
                    "bug_pattern": "SCANF_MISSING_AMP",
                    "line": 5,
                    "explanation": "thiếu &",
                    "fix_hint": "thêm &",
                },
                {"bug_pattern": "MEM_LEAK", "line": 2, "explanation": "bịa", "fix_hint": "x"},
            ],
        }


@pytest.fixture
def files(tmp_path):
    data = tmp_path / "mutants.jsonl"
    data.write_text("\n".join(json.dumps(r) for r in (REC, REC2)) + "\n")
    return data, tmp_path / "results.jsonl", tmp_path / "report.md"


def test_gold_lines_and_sampling():
    assert compare.gold_lines(REC) == {"SCANF_MISSING_AMP": 5}
    recs = [{**REC, "id": f"a{i}", "problem_id": "P1"} for i in range(5)]
    recs += [{**REC, "id": f"b{i}", "problem_id": "P2"} for i in range(5)]
    picked = compare.sample(recs, 4, seed=0)
    assert len(picked) == 4 and {r["problem_id"] for r in picked} == {"P1", "P2"}


def test_leak_heuristic():
    assert compare._leaks_solution('int x;\nscanf("%d", &x);\nreturn 0;')
    assert not compare._leaks_solution("Bạn cần thêm & trước n; như vậy scanf mới ghi được.")


def test_compare_end_to_end(files, monkeypatch):
    data, out, report = files
    fake = FakeLLM()
    monkeypatch.setattr(compare, "make_llm", lambda: FallbackLLM([fake]))
    assert compare.main(["--input", str(data), "--out", str(out), "--report", str(report)]) == 0
    rows = [json.loads(x) for x in out.read_text().splitlines()]
    assert len(rows) == 8  # 2 bài x 4 cấu hình
    by = {(r["id"], r["config"]): r for r in rows}
    # v0: cảnh báo thô; rule/hybrid: đã khử NULL_DEREF, UNINIT_VAR (hệ quả của thiếu &)
    assert by["r1", "v0"]["pred"] == ["NULL_DEREF", "SCANF_MISSING_AMP", "UNINIT_VAR"]
    assert by["r1", "rule"]["pred"] == ["SCANF_MISSING_AMP"]
    assert by["r1", "hybrid"]["provider"] == "fake" and not by["r1", "hybrid"]["fallback"]
    assert by["r1", "llm_only"]["pred"] == ["MEM_LEAK", "SCANF_MISSING_AMP"]
    assert by["r2", "rule"]["pred"] == []  # OFF_BY_ONE: công cụ không thấy
    # hybrid: giữ lỗi LLM đề xuất có dòng thật, loại lỗi không chỉ ra dòng
    assert by["r2", "hybrid"]["pred"] == ["OFF_BY_ONE"]
    assert by["r2", "hybrid"]["rejected"] == ["MEM_LEAK"]
    assert by["r1", "hybrid"]["pred"] == ["SCANF_MISSING_AMP"]

    text = report.read_text()
    assert "LLM thuần" in text and "Hybrid" in text and "fake" in text
    calls = fake.calls
    compare.main(["--input", str(data), "--out", str(out), "--report", str(report)])
    assert fake.calls == calls  # chạy lại: bỏ qua lượt đã có, không gọi LLM nữa


def test_summarize_metrics():
    rows = [
        {
            "id": "a",
            "gold": ["X"],
            "pred": ["X", "Y"],
            "gold_lines": {"X": 5},
            "pred_lines": {"X": [6]},
            "rejected": ["Z"],
            "fallback": False,
            "error": None,
            "leak": False,
            "ms": 100,
        },
        {
            "id": "b",
            "gold": ["Y"],
            "pred": ["W"],
            "gold_lines": {"Y": 3},
            "pred_lines": {},
            "rejected": [],
            "fallback": True,
            "error": None,
            "leak": True,
            "ms": 300,
        },
    ]
    s = compare.summarize(rows, vocab={"X", "Y"})
    assert s["precision"] == 0.5 and s["recall"] == 0.5  # W ngoài danh mục: không chấm
    assert s["outside_vocab"] == 1 and s["line_acc"] == 0.5 and s["exact"] == 0
    assert s["rejected"] == 1 and s["fallback"] == 0.5 and s["leak"] == 0.5
