"""Chấm chất lượng lời giải thích theo rubric: LLM-as-judge và người chấm (chấm mù).

    python -m backend.app.evaluation.rubric                      # LLM chấm mọi lời giải thích
    python -m backend.app.evaluation.rubric --export-human 12    # phiếu chấm cho người (12 bài)
    python -m backend.app.evaluation.rubric --report-only        # chỉ tổng hợp lại báo cáo

Đầu vào: data/eval/results.jsonl (lời giải thích của từng cấu hình, do compare.py sinh) và
data/mined/mutants.jsonl (code, lỗi thật đã cài). Giám khảo KHÔNG biết lời giải thích đến từ cấu
hình nào. Kết quả: data/eval/rubric.jsonl (chạy tiếp được khi bị ngắt), docs/rubric_report.md.

Người chấm: mở data/eval/human_rubric.csv (Excel / Google Sheets), điền điểm 1–5 vào các cột
tiêu chí, lưu lại dạng CSV rồi chạy --report-only. Khoá giải mã (bài nào của cấu hình nào) nằm
riêng trong data/eval/human_key.json, người chấm không mở file này.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import sys
from pathlib import Path

from ..config import ROOT
from ..llm import LLMError, make_llm
from ..problems import ProblemNotFound, ProblemRepository
from .compare import load_records

CONFIGS = ["rule", "llm_only", "hybrid"]  # v0 chỉ có cảnh báo thô, không có lời giải thích
NAMES = {"rule": "Rule-based", "llm_only": "LLM thuần", "hybrid": "Hybrid"}
CRITERIA = {
    "dung": ("Đúng", "Giải thích đúng bản chất các lỗi THẬT trong code (so với lỗi đã cài)."),
    "cu_the": (
        "Cụ thể",
        "Gắn với chính code này: chỉ ra dòng, biến, giá trị cụ thể; không chung chung.",
    ),
    "de_hieu": ("Dễ hiểu", "Sinh viên năm nhất đọc hiểu được; tiếng Việt tự nhiên, không lan man."),
    "huong_dan": ("Hướng dẫn", "Cho biết bước sửa khả thi nhưng KHÔNG đưa sẵn cả đoạn lời giải."),
    "trung_thuc": ("Không bịa", "Không nêu lỗi không có trong code, không có thông tin sai."),
}

JUDGE_SYSTEM = """Bạn là giảng viên lập trình C chấm chất lượng lời giải thích lỗi mà một trợ lý \
học tập gửi cho sinh viên năm nhất. Bạn được biết LỖI THẬT đã cài vào code (đáp án), nên hãy \
dựa vào đó để chấm, không tin vào lời giải thích.

Chấm từng tiêu chí theo thang 1–5 (1 rất kém, 3 chấp nhận được, 5 rất tốt):
{criteria}

Quy tắc:
- Thiếu hẳn một lỗi thật hoặc giải thích sai bản chất lỗi: "Đúng" tối đa 2.
- Nêu một lỗi không có trong code: "Không bịa" tối đa 2.
- Chỉ lặp lại câu mẫu chung, không nhắc gì tới code này: "Cụ thể" tối đa 2.
- Đưa nguyên đoạn code đã sửa hoàn chỉnh: "Hướng dẫn" tối đa 2.
- Chấm độc lập từng tiêu chí; độ dài không phải là chất lượng.
Trả về JSON đúng schema, nhận xét một câu ngắn bằng tiếng Việt."""


def schema() -> dict:
    props = {k: {"type": "integer", "enum": [1, 2, 3, 4, 5]} for k in CRITERIA}
    props["nhan_xet"] = {"type": "string"}
    return {
        "type": "object",
        "properties": props,
        "required": [*CRITERIA, "nhan_xet"],
        "additionalProperties": False,
    }


def numbered(source: str) -> str:
    return "\n".join(f"{i:3} | {line}" for i, line in enumerate(source.splitlines(), 1))


def truth(rec: dict) -> str:
    ops = ", ".join(rec.get("ops", [])) or "không rõ"
    return f"{', '.join(rec['labels'])} (cách cài: {ops}; số sau @ là dòng bị sửa)"


def render(expl: list[dict]) -> str:
    if not expl:
        return "(không có lời giải thích)"
    return "\n".join(
        f"- [{e['bug']}] {e['explanation']}"
        + (f"\n  Gợi ý sửa: {e['fix_hint']}" if e.get("fix_hint") else "")
        for e in expl
    )


def judge_prompt(rec: dict, statement: str, expl: list[dict]) -> str:
    return (
        f"## Đề bài\n{statement.strip()}\n\n"
        f"## Code của sinh viên\n```c\n{numbered(rec['source'])}\n```\n\n"
        f"## Lỗi thật (đáp án, sinh viên không thấy)\n{truth(rec)}\n\n"
        f"## Lời giải thích cần chấm\n{render(expl)}"
    )


def explained(results: list[dict], llm_filter: str | None) -> list[dict]:
    """Các lượt có lời giải thích; với cấu hình dùng LLM chỉ lấy lượt của `llm_filter`."""
    out = []
    for r in results:
        if r["config"] not in CONFIGS or r.get("error"):
            continue
        if r["config"] != "rule" and llm_filter and r.get("llm") != llm_filter:
            continue
        out.append(r)
    return out


def paired_ids(rows: list[dict]) -> set[str]:
    """Bài có đủ cả 3 cấu hình, để so sánh theo cặp."""
    by: dict[str, set[str]] = {}
    for r in rows:
        by.setdefault(r["id"], set()).add(r["config"])
    return {i for i, cs in by.items() if cs >= set(CONFIGS)}


# ------------------------------------------------------------ LLM-as-judge


def run_judge(rows, records, problems, llm, out: Path) -> None:
    done = set()
    if out.exists():
        done = {(r["id"], r["config"], r["gen_llm"], r["judge"]) for r in load_records(out)}
    todo = [r for r in rows if (r["id"], r["config"], r.get("llm"), llm.name) not in done]
    print(f"Chấm {len(todo)} lời giải thích (giám khảo: {llm.name})", file=sys.stderr)
    with out.open("a", encoding="utf-8") as f:
        for i, r in enumerate(todo, 1):
            rec = records[r["id"]]
            try:
                statement = problems.get(rec["problem_id"]).meta.statement
            except ProblemNotFound:
                statement = ""
            try:
                res = llm.generate(
                    JUDGE_SYSTEM.format(criteria=_criteria_text()),
                    judge_prompt(rec, statement, r["explanations"]),
                    schema(),
                )
            except LLMError as e:
                print(f"  [{i}/{len(todo)}] {r['id']} {r['config']}: lỗi {e}", file=sys.stderr)
                continue
            row = {
                "id": r["id"],
                "config": r["config"],
                "gen_llm": r.get("llm"),
                "judge": llm.name,
                "fallback": r.get("fallback", False),
                **{k: res.data[k] for k in CRITERIA},
                "nhan_xet": res.data["nhan_xet"],
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            print(f"  [{i}/{len(todo)}] {r['id']} {r['config']}", file=sys.stderr)


def _criteria_text() -> str:
    return "\n".join(f"- {name} ({k}): {desc}" for k, (name, desc) in CRITERIA.items())


# ------------------------------------------------------------ người chấm


def export_human(rows, records, n: int, seed: int, csv_path: Path, key_path: Path) -> int:
    rng = random.Random(seed)
    ids = sorted(paired_ids(rows))
    rng.shuffle(ids)
    chosen = set(ids[:n])
    items = [r for r in rows if r["id"] in chosen]
    rng.shuffle(items)  # trộn để người chấm không đoán được cấu hình theo thứ tự
    key = {}
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ma", "bai", "code", "loi_that", "giai_thich", *CRITERIA, "ghi_chu"])
        for i, r in enumerate(items, 1):
            code = f"H{i:03d}"
            key[code] = {"id": r["id"], "config": r["config"], "gen_llm": r.get("llm")}
            rec = records[r["id"]]
            w.writerow(
                [
                    code,
                    rec["problem_id"],
                    numbered(rec["source"]),
                    truth(rec),
                    render(r["explanations"]),
                    *[""] * len(CRITERIA),
                    "",
                ]
            )
    key_path.write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(items)


def load_human(csv_path: Path, key_path: Path) -> list[dict]:
    if not (csv_path.exists() and key_path.exists()):
        return []
    key = json.loads(key_path.read_text(encoding="utf-8"))
    out = []
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            scores = {}
            for k in CRITERIA:
                v = (row.get(k) or "").strip()
                if v not in {"1", "2", "3", "4", "5"}:
                    break
                scores[k] = int(v)
            else:
                if row["ma"] in key:
                    out.append({**key[row["ma"]], **scores})
    return out


# ------------------------------------------------------------ báo cáo


def _mean(xs):
    return statistics.fmean(xs) if xs else None


def _fmt(x):
    return "–" if x is None else f"{x:.2f}"


def table(scores: list[dict], title: str) -> list[str]:
    out = [
        f"### {title}",
        "",
        "| Cấu hình | n | " + " | ".join(n for n, _ in CRITERIA.values()) + " | Trung bình |",
        "|---|---|" + "---|" * (len(CRITERIA) + 1),
    ]
    for c in CONFIGS:
        rs = [s for s in scores if s["config"] == c]
        if not rs:
            continue
        per = [_mean([s[k] for s in rs]) for k in CRITERIA]
        overall = _mean([statistics.fmean(s[k] for k in CRITERIA) for s in rs])
        out.append(
            f"| {NAMES[c]} | {len(rs)} | "
            + " | ".join(map(_fmt, per))
            + f" | **{_fmt(overall)}** |"
        )
    return out + [""]


def paired_wins(scores: list[dict], a: str, b: str) -> tuple[int, int, int]:
    """Số bài a hơn / hoà / thua b theo điểm trung bình 5 tiêu chí."""
    avg = {(s["id"], s["config"]): statistics.fmean(s[k] for k in CRITERIA) for s in scores}
    win = tie = lose = 0
    for i in {s["id"] for s in scores}:
        if (i, a) in avg and (i, b) in avg:
            d = avg[(i, a)] - avg[(i, b)]
            win, tie, lose = win + (d > 0), tie + (d == 0), lose + (d < 0)
    return win, tie, lose


def agreement(a: list[dict], b: list[dict], title: str, label: str) -> list[str]:
    """Độ khớp điểm giữa hai bên chấm trên các lời giải thích cả hai cùng chấm."""
    b_by = {(s["id"], s["config"]): s for s in b}
    pairs = [(x, b_by[(x["id"], x["config"])]) for x in a if (x["id"], x["config"]) in b_by]
    if len(pairs) < 3:
        return []
    out = [
        f"### {title}",
        "",
        f"{len(pairs)} lời giải thích được {label}.",
        "",
        "| Tiêu chí | Tương quan Pearson | Lệch tuyệt đối trung bình |",
        "|---|---|---|",
    ]
    for k, (name, _) in CRITERIA.items():
        h, m = [p[0][k] for p in pairs], [p[1][k] for p in pairs]
        try:
            r = f"{statistics.correlation(h, m):.2f}"
        except statistics.StatisticsError:
            r = "– (một bên chấm mọi bài như nhau)"
        mae = statistics.fmean(abs(x - y) for x, y in zip(h, m, strict=True))
        out.append(f"| {name} | {r} | {mae:.2f} |")
    return out + [""]


def judge_section(scores: list[dict], judge: str) -> list[str]:
    ids = paired_ids(scores)
    paired = [s for s in scores if s["id"] in ids]
    if not paired:
        return []
    out = table(paired, f"LLM-as-judge ({judge}), {len(ids)} bài có đủ 3 cấu hình")
    out += ["| So sánh theo từng bài | Hơn | Hoà | Kém |", "|---|---|---|---|"]
    for a, b in (("hybrid", "rule"), ("hybrid", "llm_only")):
        w, t, lo = paired_wins(paired, a, b)
        out.append(f"| {NAMES[a]} so với {NAMES[b]} | {w} | {t} | {lo} |")
    fb = [s for s in paired if s["config"] == "hybrid" and s.get("fallback")]
    return out + [
        "",
        f"Trong đó {len(fb)} lượt Hybrid phải lùi về giải thích bằng luật (LLM lỗi).",
        "",
    ]


def write_report(
    path: Path, by_judge: dict[str, list[dict]], human: list[dict], gen: str | None
) -> None:
    out = [
        "# Chất lượng lời giải thích (rubric)",
        "",
        "> Sinh tự động bởi `python -m backend.app.evaluation.rubric`. Không sửa tay.",
        "",
        f"Lời giải thích của LLM thuần và Hybrid sinh bởi {gen or '–'}. Thang 1–5 cho mỗi "
        "tiêu chí; giám khảo không biết lời giải thích đến từ cấu hình nào.",
        "",
        *[f"- **{name}**: {desc}" for name, desc in CRITERIA.values()],
        "",
    ]
    for judge, scores in by_judge.items():
        out += judge_section(scores, judge)
    judges = list(by_judge)
    for i, a in enumerate(judges):
        for b in judges[i + 1 :]:
            out += agreement(
                by_judge[a],
                by_judge[b],
                f"Độ khớp giữa hai giám khảo: {a} và {b}",
                "cả hai giám khảo chấm",
            )
    if human:
        out += table(human, f"Người chấm, {len({h['id'] for h in human})} bài")
        for judge, scores in by_judge.items():
            out += agreement(
                human, scores, f"Độ khớp giữa người chấm và {judge}", "cả hai bên chấm"
            )
    same = [j for j in judges if gen and j.split(":", 1)[-1] in gen]
    out += [
        "## Lưu ý khi đọc",
        "",
        "- Giám khảo LLM có thể ưu ái văn phong LLM (self-preference), nhất là khi cùng model với "
        "bên sinh lời giải thích"
        + (f" (ở đây: {', '.join(same)})" if same else "")
        + ". Vì vậy cần đối chiếu giữa các giám khảo và với người chấm (các bảng độ khớp).",
        '- Rule-based dùng câu gợi ý cố định theo mã lỗi, nên điểm "Cụ thể" thấp là đúng thiết kế.',
        "- Lỗi do máy cài vào lời giải mẫu, chưa phải bài làm thật của sinh viên.",
    ]
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results", type=Path, default=ROOT / "data/eval/results.jsonl")
    ap.add_argument("--input", type=Path, default=ROOT / "data/mined/mutants.jsonl")
    ap.add_argument("--out", type=Path, default=ROOT / "data/eval/rubric.jsonl")
    ap.add_argument("--report", type=Path, default=ROOT / "docs/rubric_report.md")
    ap.add_argument("--gen-llm", default=None, help="chỉ chấm lời giải thích sinh bởi LLM này")
    ap.add_argument("--export-human", type=int, metavar="N", help="xuất phiếu chấm N bài cho người")
    ap.add_argument("--human-csv", type=Path, default=ROOT / "data/eval/human_rubric.csv")
    ap.add_argument("--human-key", type=Path, default=ROOT / "data/eval/human_key.json")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    records = {r["id"]: r for r in load_records(args.input)}
    results = [r for r in load_records(args.results) if r["id"] in records]
    gen = args.gen_llm or next((r["llm"] for r in results if r.get("llm")), None)
    rows = explained(results, gen)

    if args.export_human:
        n = export_human(
            rows, records, args.export_human, args.seed, args.human_csv, args.human_key
        )
        print(f"Phiếu chấm {n} dòng -> {args.human_csv}; khoá -> {args.human_key}")
        return 0

    if not args.report_only:
        llm = make_llm()
        if llm is None:
            print("Chưa cấu hình LLM (LLM_PROVIDERS).", file=sys.stderr)
            return 1
        args.out.parent.mkdir(parents=True, exist_ok=True)
        run_judge(rows, records, ProblemRepository(ROOT / "data/problems"), llm, args.out)

    by_judge: dict[str, list[dict]] = {}
    if args.out.exists():
        for s in load_records(args.out):
            if s["gen_llm"] in (gen, None):
                by_judge.setdefault(s["judge"], []).append(s)
    human = load_human(args.human_csv, args.human_key)
    write_report(args.report, by_judge, human, gen)
    print(f"Báo cáo -> {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
