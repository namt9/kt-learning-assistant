"""Kiểm tra tri thức và nạp Knowledge Graph vào Neo4j.

python -m backend.app.kg.load --check          # chỉ kiểm tra YAML, không cần Neo4j
python -m backend.app.kg.load                  # kiểm tra + nạp phần tĩnh + log nộp bài
python -m backend.app.kg.load --reset          # xoá đồ thị cũ rồi nạp lại từ đầu
"""

from __future__ import annotations

import argparse
import sys

from ..config import ROOT, load_settings
from .loader import load_static, load_submissions, reset
from .model import KnowledgeBase
from .queries import connect


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--check", action="store_true", help="chỉ kiểm tra tính nhất quán")
    ap.add_argument("--reset", action="store_true", help="xoá đồ thị cũ trước khi nạp")
    ap.add_argument("--no-submissions", action="store_true", help="không nạp log nộp bài")
    ap.add_argument("--quiet", action="store_true", help="không in cảnh báo")
    args = ap.parse_args(argv)

    settings = load_settings()
    kb = KnowledgeBase.load(ROOT / "knowledge", settings.problems_dir)
    report = kb.validate()
    print(
        f"Tri thức: {len(kb.concepts)} concept, {len(kb.bug_patterns)} bug pattern, "
        f"{len(kb.actions)} hành động sư phạm, {len(kb.problems)} bài tập"
    )
    for e in report.errors:
        print(f"  LỖI      {e}")
    if not args.quiet:
        for w in report.warnings:
            print(f"  cảnh báo {w}")
    if not report.ok:
        print(f"Dừng: {len(report.errors)} lỗi cần sửa trong knowledge/*.yaml")
        return 1
    if args.check:
        print(f"OK ({len(report.warnings)} cảnh báo)")
        return 0

    with connect() as driver, driver.session() as session:
        if args.reset:
            reset(session)
        counts = load_static(session, kb)
        print("Đã nạp phần tĩnh:", ", ".join(f"{k}={v}" for k, v in counts.items()))
        if not args.no_submissions:
            n = load_submissions(session, settings.db_path)
            print(f"Đã nạp {n} lần nộp bài từ {settings.db_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
