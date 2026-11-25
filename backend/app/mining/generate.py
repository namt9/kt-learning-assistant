"""Sinh log có nhãn: cài lỗi vào lời giải mẫu rồi chấm từng biến thể bằng hệ v0.

    python -m backend.app.mining.generate --out data/mined/mutants.jsonl --pairs 40 --jobs 4

Mỗi dòng JSONL là một bài nộp giả lập: mã nguồn, lỗi đã cài (nhãn đúng), verdict và các lỗi
mà tầng luật phát hiện được. Chạy theo SANDBOX_MODE trong .env (mặc định docker).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..config import load_settings
from ..judge.judge import Judge
from ..judge.runner import make_runner
from ..problems import ProblemRepository
from ..rules.catalog import Catalog
from ..schemas import Language, Submission
from .mutate import Mutant, pair_mutants, single_mutants


def _record(judge: Judge, problem, m: Mutant) -> dict:
    rep = judge.evaluate(
        Submission(student_id="mutant", problem_id=problem.meta.id, language=Language.C,
                   source_code=m.source),
        problem,
    )  # fmt: skip
    return {
        "id": hashlib.sha1(m.source.encode()).hexdigest()[:12],
        "problem_id": problem.meta.id,
        "concepts": problem.meta.concepts,
        "labels": list(m.labels),
        "ops": list(m.ops),
        "verdict": rep.grading.verdict.value,
        "score": rep.grading.score,
        "findings": [
            {"bug_pattern": f.bug_pattern, "source": f.source, "line": f.line} for f in rep.findings
        ],
        "tools_unavailable": rep.tools_unavailable,
        "source": m.source,
        # báo cáo chấm đầy đủ (test mẫu, thông báo biên dịch) để script đánh giá đưa cùng một
        # ngữ cảnh cho mọi cấu hình chẩn đoán
        "report": rep.model_dump(mode="json"),
    }


def dedupe(mutants: list[Mutant]) -> list[Mutant]:
    """Bỏ biến thể trùng mã nguồn, giữ cách cài lỗi ít thao tác nhất.

    Hai cách cài khác nhau có thể ra cùng một đoạn code (ví dụ free sớm rồi xoá free = chỉ xoá
    free). Nhãn đúng của đoạn code đó là lời giải thích ngắn nhất; nhãn của cách dài hơn là sai.
    """
    best: dict[str, Mutant] = {}
    for m in mutants:
        if m.source not in best or len(m.ops) < len(best[m.source].ops):
            best[m.source] = m
    return list(best.values())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("data/mined/mutants.jsonl"))
    ap.add_argument("--pairs", type=int, default=40, help="số biến thể 2 lỗi cho mỗi bài")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--jobs", type=int, default=4, help="số bài chấm song song")
    args = ap.parse_args(argv)

    s = load_settings()
    problems = ProblemRepository(s.problems_dir)
    runner = make_runner(s.sandbox_mode, s.sandbox_image, s.max_output_bytes)
    judge = Judge(runner, Catalog(s.bug_patterns_file), s.work_dir, s.compile_timeout_s)

    jobs = []
    for summary in problems.list():
        problem = problems.get(summary.id)
        solution = s.problems_dir.glob(f"{summary.id}_*/solution.c")
        src = next(solution).read_text(encoding="utf-8")
        for m in dedupe(single_mutants(src) + pair_mutants(src, args.pairs, args.seed)):
            jobs.append((problem, m))
    print(f"Chấm {len(jobs)} biến thể ({s.sandbox_mode})...", file=sys.stderr)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    done = 0
    with ThreadPoolExecutor(args.jobs) as pool, args.out.open("w", encoding="utf-8") as f:
        for rec in pool.map(lambda job: _record(judge, *job), jobs):
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            done += 1
            if done % 20 == 0:
                print(f"  {done}/{len(jobs)}", file=sys.stderr)
    print(f"Đã ghi {done} bản ghi vào {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
