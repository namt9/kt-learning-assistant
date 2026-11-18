"""So sánh các cấu hình chẩn đoán trên benchmark có nhãn (data/mined/mutants.jsonl).

    python -m backend.app.evaluation.compare                       # cả 4 cấu hình, mọi bài
    python -m backend.app.evaluation.compare --limit 30            # thử nhanh 30 bài
    LLM_PROVIDERS=ollama python -m backend.app.evaluation.compare  # chọn LLM

Cấu hình (cùng đầu vào: đề bài, mã nguồn, kết quả chấm):

    v0        cảnh báo thô của công cụ (hệ nền), chưa khử nhiễu
    rule      luật + luật khai phá khử nhiễu + KG, không LLM
    llm_only  LLM tự tìm lỗi từ code (không thấy kết quả của luật, không có KG)
    hybrid    luật xác định lỗi, KG cấp tri thức, LLM giải thích

Kết quả từng bài ghi dần vào data/eval/results.jsonl; chạy lại sẽ bỏ qua những (bài, cấu hình,
LLM) đã có, nên có thể dừng giữa chừng rồi chạy tiếp (LLM chậm hoặc tốn phí).
Báo cáo tổng hợp: docs/eval_report.md.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import sys
import time
from pathlib import Path

from ..agents.diagnosis import DiagnosisAgent
from ..config import ROOT
from ..kg.model import KnowledgeBase
from ..kg.offline import OfflineKG
from ..llm import LLMError, make_llm
from ..problems import ProblemNotFound, ProblemRepository
from ..rules.catalog import Catalog
from ..rules.mined import MinedRules
from ..schemas import DiagnosisMode, GradingResult, SubmissionReport, Verdict

CONFIGS = ["v0", "rule", "llm_only", "hybrid"]
NEEDS_LLM = {"llm_only", "hybrid"}
LINE_TOLERANCE = 1  # đoán lệch 1 dòng vẫn tính đúng (lỗi thường trải qua dòng kề)


# ------------------------------------------------------------ dữ liệu


def load_records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def gold_lines(rec: dict) -> dict[str, int]:
    """Dòng bị cài lỗi, lấy từ ops ("drop_amp@5") theo đúng thứ tự labels."""
    out = {}
    for bug, op in zip(rec["labels"], rec.get("ops", []), strict=False):
        m = re.search(r"@(\d+)$", op)
        if m:
            out.setdefault(bug, int(m.group(1)))
    return out


def to_report(rec: dict) -> SubmissionReport:
    if "report" in rec:
        return SubmissionReport.model_validate(rec["report"])
    # bản ghi cũ chưa lưu báo cáo đầy đủ: dựng lại phần tối thiểu
    from ..schemas import Finding, Language

    return SubmissionReport(
        submission_id=rec["id"],
        student_id="eval",
        problem_id=rec["problem_id"],
        language=Language.C,
        created_at="2026-11-18T00:00:00+00:00",
        grading=GradingResult(
            submission_id=rec["id"], verdict=Verdict(rec["verdict"]), score=rec.get("score", 0)
        ),
        findings=[
            Finding(
                bug_pattern=f["bug_pattern"],
                source=f["source"],
                line=f["line"],
                message=f["bug_pattern"],
            )
            for f in rec["findings"]
        ],
    )


def sample(records: list[dict], limit: int | None, seed: int) -> list[dict]:
    """Lấy mẫu đều theo bài tập để mỗi bài đều có mặt khi chỉ chạy một phần."""
    if not limit or limit >= len(records):
        return records
    rng = random.Random(seed)
    by_problem: dict[str, list[dict]] = {}
    for r in records:
        by_problem.setdefault(r["problem_id"], []).append(r)
    for rs in by_problem.values():
        rng.shuffle(rs)
    out, i = [], 0
    while len(out) < limit:
        for rs in by_problem.values():
            if i < len(rs) and len(out) < limit:
                out.append(rs[i])
        i += 1
    return out


# ------------------------------------------------------------ chạy một bài với một cấu hình


def _leaks_solution(text: str) -> bool:
    """Lời giải thích chứa từ 3 dòng trông như code C -> có nguy cơ viết hộ lời giải."""
    code_like = [ln for ln in text.splitlines() if re.search(r"[;{}]\s*$", ln.strip())]
    return len(code_like) >= 3


def run_one(
    rec: dict, config: str, agent: DiagnosisAgent, mined: MinedRules, problems: ProblemRepository
) -> dict:
    report = to_report(rec)
    source = rec["source"]
    try:
        problem = problems.get(rec["problem_id"])
    except ProblemNotFound:
        problem = None
    out = {
        "id": rec["id"],
        "config": config,
        "problem_id": rec["problem_id"],
        "gold": rec["labels"],
        "gold_lines": gold_lines(rec),
        "pred": [],
        "pred_lines": {},
        "provider": None,
        "fallback": False,
        "rejected": [],
        "error": None,
        "ms": 0,
        "leak": False,
        "explanations": [],
    }

    if config == "v0":
        found = report.findings
    else:
        report.findings = mined.apply(report, source)
        found = [f for f in report.findings if not f.suppressed_by]

    t = time.perf_counter()
    if config in ("v0", "rule", "hybrid"):
        lines: dict[str, list[int]] = {}
        for f in found:
            lines.setdefault(f.bug_pattern, []).extend([f.line] if f.line else [])
        out["pred"], out["pred_lines"] = sorted(lines), lines
    if config in ("rule", "hybrid", "llm_only"):
        mode = {
            "rule": DiagnosisMode.RULE,
            "hybrid": DiagnosisMode.HYBRID,
            "llm_only": DiagnosisMode.LLM_ONLY,
        }[config]
        try:
            d = agent.diagnose(report, source, problem, mode)
        except LLMError as e:
            out["error"] = str(e)
        else:
            out["provider"], out["rejected"] = d.llm_provider, d.rejected
            out["fallback"] = d.mode != mode
            out["explanations"] = [
                {"bug": it.bug_pattern, "explanation": it.explanation, "fix_hint": it.fix_hint}
                for it in d.items
            ]
            out["leak"] = any(
                _leaks_solution(e["explanation"] + "\n" + e["fix_hint"])
                for e in out["explanations"]
            )
            if config == "llm_only":
                lines = {}
                for f in d.findings:
                    lines.setdefault(f.bug_pattern, []).extend([f.line] if f.line else [])
                out["pred"], out["pred_lines"] = sorted(lines), lines
    out["ms"] = int((time.perf_counter() - t) * 1000)
    return out


# ------------------------------------------------------------ tổng hợp


def summarize(results: list[dict], vocab: set[str]) -> dict:
    """Chỉ số của một cấu hình. Dự đoán ngoài `vocab` (mã không có nhãn đúng) không chấm được."""
    tp = fp = fn = exact = line_ok = line_total = outside = 0
    for r in results:
        gold, pred = set(r["gold"]), set(r["pred"])
        outside += len(pred - vocab)
        pred &= vocab
        tp += len(pred & gold)
        fp += len(pred - gold)
        fn += len(gold - pred)
        exact += pred == gold
        for bug, line in r["gold_lines"].items():
            line_total += 1
            line_ok += any(abs(x - line) <= LINE_TOLERANCE for x in r["pred_lines"].get(bug, []))
    n = len(results) or 1
    p = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    ms = [r["ms"] for r in results]
    return {
        "n": len(results),
        "precision": p,
        "recall": rec,
        "f1": 2 * p * rec / (p + rec) if p + rec else 0.0,
        "exact": exact / n,
        "line_acc": line_ok / line_total if line_total else 0.0,
        "outside_vocab": outside,
        "rejected": sum(len(r["rejected"]) for r in results),
        "fallback": sum(r["fallback"] for r in results) / n,
        "errors": sum(bool(r["error"]) for r in results) / n,
        "leak": sum(r["leak"] for r in results) / n,
        "ms_median": statistics.median(ms) if ms else 0,
        "ms_mean": statistics.fmean(ms) if ms else 0,
    }


def write_report(path: Path, results: list[dict], vocab: set[str], meta: dict) -> dict:
    by_cfg = {c: [r for r in results if r["config"] == c] for c in CONFIGS}
    # chỉ so trên những bài mà MỌI cấu hình đã chạy, để các cột so được với nhau
    common = set.intersection(*[{r["id"] for r in rs} for rs in by_cfg.values() if rs] or [set()])
    stats = {
        c: summarize([r for r in rs if r["id"] in common], vocab) for c, rs in by_cfg.items() if rs
    }
    names = {
        "v0": "v0: công cụ thô",
        "rule": "Rule-based",
        "llm_only": "LLM thuần",
        "hybrid": "Hybrid",
    }
    pct = lambda x: f"{x:.0%}"  # noqa: E731
    out = [
        "# So sánh LLM thuần / Rule-based / Hybrid",
        "",
        "> Sinh tự động bởi `python -m backend.app.evaluation.compare`. Không sửa tay.",
        "",
        f"- Dữ liệu: {len(common)} bài nộp có nhãn đúng (`{meta['input']}`), mỗi bài chạy qua mọi "
        "cấu hình bên dưới.",
        f"- LLM: {meta['llm'] or 'không có'}.",
        "- Precision / recall / F1 tính trên các mã lỗi có nhãn đúng; dòng đúng: chỉ ra dòng "
        f"bị cài lỗi, lệch tối đa {LINE_TOLERANCE} dòng.",
        "",
        "## Xác định lỗi",
        "",
        "| Cấu hình | P | R | F1 | Đúng hoàn toàn | Dòng đúng | Mã ngoài danh mục |",
        "|---|---|---|---|---|---|---|",
    ]
    for c, s in stats.items():
        out.append(
            f"| {names[c]} | {s['precision']:.2f} | {s['recall']:.2f} | {s['f1']:.2f} | "
            f"{pct(s['exact'])} | {pct(s['line_acc'])} | {s['outside_vocab']} |"
        )
    out += [
        "",
        "## Độ tin cậy và chi phí",
        "",
        "| Cấu hình | Mã LLM bịa bị chặn | Lùi về luật | Lỗi LLM | Nghi lộ lời giải | "
        "Thời gian (trung vị / trung bình) |",
        "|---|---|---|---|---|---|",
    ]
    for c, s in stats.items():
        if c == "v0":
            continue
        out.append(
            f"| {names[c]} | {s['rejected']} | {pct(s['fallback'])} | {pct(s['errors'])} | "
            f"{pct(s['leak'])} | {s['ms_median'] / 1000:.1f}s / {s['ms_mean'] / 1000:.1f}s |"
        )
    # recall theo từng lỗi
    bugs = sorted({b for r in results if r["id"] in common for b in r["gold"]})
    out += [
        "",
        "## Recall theo loại lỗi",
        "",
        "| Lỗi | Số bài | " + " | ".join(names[c] for c in stats) + " |",
        "|---|---|" + "---|" * len(stats),
    ]
    for b in bugs:
        cells = []
        for c in stats:
            rs = [r for r in by_cfg[c] if r["id"] in common and b in r["gold"]]
            cells.append(pct(sum(b in r["pred"] for r in rs) / len(rs)) if rs else "–")
        gold_by_id = {r["id"]: r["gold"] for r in results if r["id"] in common}
        n_b = sum(b in g for g in gold_by_id.values())
        out.append(f"| {b} | {n_b} | " + " | ".join(cells) + " |")
    out += [
        "",
        "## Đọc kết quả",
        "",
        "- Rule-based và Hybrid xác định lỗi giống nhau (cùng tầng luật); khác nhau ở chất lượng "
        "giải thích, cần chấm thêm theo rubric (LLM-as-judge + người chấm).",
        '- "Nghi lộ lời giải" là kiểm tra tự động thô (từ 3 dòng trông như code trong lời giải '
        "thích); cần người đọc lại các trường hợp bị đánh dấu.",
        "- Rule-based và Hybrid dùng luật khử nhiễu khai phá từ chính tập dữ liệu này, nên số đo "
        "trên đây lạc quan (đánh giá trên dữ liệu đã học). Số đo trên bài chưa thấy: xem phần "
        "leave-one-problem-out trong `docs/mining_report.md`.",
        '- "Dòng đúng" so với dòng bị cài lỗi; công cụ thường báo dòng lỗi biểu hiện (ví dụ bỏ '
        "`= 0` ở dòng khai báo nhưng gcc báo ở dòng cộng dồn), nên chỉ số này thấp hơn thực tế.",
        "- Lỗi do máy cài vào lời giải mẫu, chưa phải bài làm thật của sinh viên.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out), encoding="utf-8")
    return stats


# ------------------------------------------------------------ CLI


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--input", type=Path, default=ROOT / "data/mined/mutants.jsonl")
    ap.add_argument("--out", type=Path, default=ROOT / "data/eval/results.jsonl")
    ap.add_argument("--report", type=Path, default=ROOT / "docs/eval_report.md")
    ap.add_argument("--configs", default=",".join(CONFIGS))
    ap.add_argument("--limit", type=int, default=None, help="chỉ chạy N bài (lấy mẫu đều)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    records = sample(load_records(args.input), args.limit, args.seed)
    vocab = {b for r in load_records(args.input) for b in r["labels"]}
    configs = [c.strip() for c in args.configs.split(",") if c.strip()]
    kb = KnowledgeBase.load(ROOT / "knowledge", ROOT / "data/problems")
    catalog = Catalog(ROOT / "knowledge/bug_patterns.yaml")
    mined = MinedRules.load(ROOT / "knowledge/mined_rules.yaml")
    problems = ProblemRepository(ROOT / "data/problems")
    llm = make_llm()
    llm_name = llm.name if llm else None
    if llm is None and NEEDS_LLM & set(configs):
        print("Chưa cấu hình LLM: bỏ qua llm_only, hybrid.", file=sys.stderr)
        configs = [c for c in configs if c not in NEEDS_LLM]
    agent = DiagnosisAgent(catalog, OfflineKG(kb), llm)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if args.out.exists():
        for r in load_records(args.out):
            done.add((r["id"], r["config"], r.get("llm")))
    todo = [
        (rec, c)
        for rec in records
        for c in configs
        if (rec["id"], c, llm_name if c in NEEDS_LLM else None) not in done
    ]
    print(
        f"{len(records)} bài x {len(configs)} cấu hình: còn {len(todo)} lượt "
        f"(LLM: {llm_name or 'không'})",
        file=sys.stderr,
    )
    with args.out.open("a", encoding="utf-8") as f:
        for i, (rec, c) in enumerate(todo, 1):
            res = run_one(rec, c, agent, mined, problems)
            res["llm"] = llm_name if c in NEEDS_LLM else None
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
            f.flush()
            if c in NEEDS_LLM or i % 50 == 0:
                print(
                    f"  [{i}/{len(todo)}] {rec['id']} {c}: {res['ms'] / 1000:.1f}s"
                    + (f" lỗi: {res['error']}" if res["error"] else ""),
                    file=sys.stderr,
                )

    ids = {r["id"] for r in records}
    results = [
        r
        for r in load_records(args.out)
        if r["id"] in ids and (r["config"] not in NEEDS_LLM or r.get("llm") == llm_name)
    ]
    stats = write_report(args.report, results, vocab, {"input": args.input.name, "llm": llm_name})
    for c, s in stats.items():
        print(
            f"{c:9s} P {s['precision']:.2f} R {s['recall']:.2f} F1 {s['f1']:.2f} "
            f"dòng {s['line_acc']:.0%} lùi {s['fallback']:.0%} lỗi {s['errors']:.0%} "
            f"{s['ms_median'] / 1000:.1f}s"
        )
    print(f"Báo cáo -> {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
