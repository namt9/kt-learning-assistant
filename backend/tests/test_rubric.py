"""Chấm rubric: LLM-as-judge (dùng LLM giả), phiếu chấm mù cho người, độ khớp hai bên."""

import csv
import json

import pytest

from backend.app.evaluation import rubric
from backend.app.llm.base import FallbackLLM

SRC = '#include <stdio.h>\nint main(void) {\n    int n;\n    scanf("%d", n);\n    return 0;\n}\n'


class FakeJudge:
    """Chấm cao lời giải thích có nhắc tới dòng cụ thể, thấp nếu không."""

    name = "fake:judge"

    def __init__(self):
        self.calls = 0

    def generate_json(self, system, user, schema):
        self.calls += 1
        assert "Lỗi thật" in user and "SCANF_MISSING_AMP" in user
        assert "hybrid" not in user and "llm_only" not in user  # giám khảo chấm mù
        good = "dòng 4" in user.split("Lời giải thích cần chấm")[1]
        score = 5 if good else 2
        return {**{k: score for k in rubric.CRITERIA}, "nhan_xet": "ok"}


def _result(rid, config, text, llm="ollama:x"):
    return {
        "id": rid,
        "config": config,
        "llm": None if config == "rule" else llm,
        "error": None,
        "fallback": False,
        "explanations": [{"bug": "SCANF_MISSING_AMP", "explanation": text, "fix_hint": "thêm &"}],
    }


@pytest.fixture
def files(tmp_path):
    mutants = tmp_path / "mutants.jsonl"
    results = tmp_path / "results.jsonl"
    recs, res = [], []
    for i in range(4):
        rid = f"r{i}"
        recs.append(
            {
                "id": rid,
                "problem_id": "P001",
                "labels": ["SCANF_MISSING_AMP"],
                "ops": ["drop_amp@4"],
                "source": SRC,
            }
        )
        res += [
            _result(rid, "v0", "bỏ qua"),
            _result(rid, "rule", "scanf cần địa chỉ của biến."),
            _result(rid, "llm_only", "Biến n chưa khởi tạo."),
            _result(rid, "hybrid", "Ở dòng 4, scanf nhận n thay vì &n."),
            _result(rid, "hybrid", "của LLM khác", llm="claude:y"),
        ]
    mutants.write_text("\n".join(json.dumps(r) for r in recs))
    results.write_text("\n".join(json.dumps(r) for r in res))
    return tmp_path


def args(d, *extra):
    return [
        "--input",
        str(d / "mutants.jsonl"),
        "--results",
        str(d / "results.jsonl"),
        "--out",
        str(d / "rubric.jsonl"),
        "--report",
        str(d / "report.md"),
        "--human-csv",
        str(d / "human.csv"),
        "--human-key",
        str(d / "key.json"),
        "--gen-llm",
        "ollama:x",
        *extra,
    ]


def test_llm_judge_scores_blind_and_resumes(files, monkeypatch):
    fake = FakeJudge()
    monkeypatch.setattr(rubric, "make_llm", lambda: FallbackLLM([fake]))
    assert rubric.main(args(files)) == 0
    assert fake.calls == 12  # 4 bài x 3 cấu hình; bỏ v0 và lời giải thích của LLM khác
    scores = [json.loads(line) for line in (files / "rubric.jsonl").read_text().splitlines()]
    assert {s["config"] for s in scores} == {"rule", "llm_only", "hybrid"}
    assert all(s["dung"] == (5 if s["config"] == "hybrid" else 2) for s in scores)
    report = (files / "report.md").read_text()
    assert "| Hybrid | 4 | 5.00" in report and "| Hybrid so với Rule-based | 4 | 0 | 0 |" in report

    assert rubric.main(args(files)) == 0  # chạy lại: không chấm lại
    assert fake.calls == 12


def test_human_sheet_roundtrip_and_agreement(files, monkeypatch):
    fake = FakeJudge()
    monkeypatch.setattr(rubric, "make_llm", lambda: FallbackLLM([fake]))
    rubric.main(args(files))
    assert rubric.main(args(files, "--export-human", "3")) == 0
    with (files / "human.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 9 and all(r["ma"].startswith("H") for r in rows)
    assert not any("hybrid" in " ".join(r.values()) for r in rows)  # không lộ cấu hình
    key = json.loads((files / "key.json").read_text())
    # người chấm đồng ý với giám khảo LLM, trừ một dòng bỏ trống (không tính)
    for i, r in enumerate(rows):
        s = "5" if key[r["ma"]]["config"] == "hybrid" else "2"
        for k in rubric.CRITERIA:
            r[k] = "" if i == 0 else s
    with (files / "human.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    assert rubric.main(args(files, "--report-only")) == 0
    report = (files / "report.md").read_text()
    assert "Người chấm" in report and "8 lời giải thích được cả hai bên chấm" in report
    assert "| Đúng | 1.00 | 0.00 |" in report


def test_two_judges_each_get_a_section_and_agreement(files, monkeypatch):
    a, b = FakeJudge(), FakeJudge()
    b.name = "fake:other"
    monkeypatch.setattr(rubric, "make_llm", lambda: FallbackLLM([a]))
    rubric.main(args(files))
    monkeypatch.setattr(rubric, "make_llm", lambda: FallbackLLM([b]))
    rubric.main(args(files))
    assert b.calls == 12  # giám khảo mới chấm lại đủ, không dùng điểm của giám khảo cũ
    report = (files / "report.md").read_text()
    assert "LLM-as-judge (fake:judge)" in report and "LLM-as-judge (fake:other)" in report
    assert "Độ khớp giữa hai giám khảo: fake:judge và fake:other" in report
