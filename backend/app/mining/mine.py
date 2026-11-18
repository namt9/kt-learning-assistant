"""Khai phá luật chẩn đoán từ log có nhãn và đánh giá chúng.

    python -m backend.app.mining.mine --input data/mined/mutants.jsonl

Mỗi bài nộp thành một giao dịch gồm các mục quan sát được và nhãn đúng:

    verdict=WA          kết quả chấm
    found=UNINIT_VAR    lỗi tầng luật phát hiện (found=NONE nếu không phát hiện gì)
    feat=malloc         đặc trưng code (có malloc, có free, có phép chia, ...)
    concept=mang        khái niệm của bài tập
    bug=OFF_BY_ONE      lỗi thật đã cài (chỉ có ở dữ liệu có nhãn)
    fp=NULL_DEREF       công cụ báo NULL_DEREF nhưng đó không phải lỗi thật (báo sai / hệ quả)

Hai loại luật, vế trái chỉ gồm mục quan sát được:

- luật bổ sung {...} -> bug=X  : đoán lỗi thật mà công cụ bỏ sót hoặc gọi sai tên;
- luật khử nhiễu {found=A, ...} -> fp=A : A chỉ là hệ quả của lỗi gốc khác (ví dụ thiếu & trong
  scanf làm chương trình đọc biến chưa khởi tạo rồi crash), nên bỏ A khỏi chẩn đoán.

Đầu ra: knowledge/mined_rules.yaml (luật, dùng cho rule engine / KG) và docs/mining_report.md.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

import yaml

from ..config import ROOT
from ..rules.custom import strip_comments_and_strings
from .apriori import Rule, association_rules, frequent_itemsets, prune_redundant

FEATURES = {
    "malloc": r"\b(?:malloc|calloc|realloc)\s*\(",
    "free": r"\bfree\s*\(",
    "scanf": r"\bscanf\s*\(",
    "for": r"\bfor\s*\(",
    "while": r"\bwhile\s*\(",
    "if": r"\bif\s*\(",
    "array_index": r"\w\s*\[",
    "division": r"[\w)\s]/[^/=*]",
    "cast": r"\(\s*(?:double|float|int|long)\s*\)",
    "long_long": r"\blong\s+long\b",
    "double": r"\bdouble\b",
}


def code_features(source: str) -> set[str]:
    code = strip_comments_and_strings(source)
    feats = {name for name, pat in FEATURES.items() if re.search(pat, code)}
    if "malloc" in feats and "free" not in feats:
        feats.add("malloc_no_free")
    return feats


def transaction(
    rec: dict, with_labels: bool = True, label_vocab: set[str] | None = None
) -> frozenset[str]:
    items = {f"verdict={rec['verdict']}"}
    found = {f["bug_pattern"] for f in rec["findings"]}
    items |= {f"found={b}" for b in found} or {"found=NONE"}
    items |= {f"feat={f}" for f in code_features(rec["source"])}
    items |= {f"concept={c}" for c in rec.get("concepts", [])}
    if with_labels:
        labels = set(rec.get("labels", []))
        items |= {f"bug={b}" for b in labels}
        # chỉ biết chắc "báo sai" với mã lỗi có trong bộ nhãn; mã không bao giờ được cài
        # (CONST_CONDITION, UNCLASSIFIED, ...) thì không có nhãn nào để so -> không kết luận
        vocab = label_vocab if label_vocab is not None else labels
        items |= {f"fp={b}" for b in (found - labels) & vocab}
    return frozenset(items)


def _observable(item: str) -> bool:
    # concept= gần như cố định trong mỗi bài, thực chất là mã bài tập -> luật học thuộc bài
    return not item.startswith(("bug=", "fp=", "concept="))


def rule_kind(r: Rule) -> str:
    return "suppress" if r.consequent.startswith("fp=") else "add"


def rule_bug(r: Rule) -> str:
    return r.consequent.split("=", 1)[1]


def _useful(r: Rule) -> bool:
    found_target = f"found={rule_bug(r)}" in r.antecedent
    if rule_kind(r) == "add":
        return not found_target  # {found=X} -> bug=X chỉ xác nhận công cụ, không thêm tri thức
    # Luật khử nhiễu mô tả quan hệ giữa các cảnh báo (lỗi gốc kéo theo cảnh báo hệ quả), nên
    # vế trái chỉ gồm cảnh báo và verdict; đặc trưng code ở đây chỉ khiến luật học thuộc từng bài.
    signals_only = all(i.startswith(("found=", "verdict=")) for i in r.antecedent)
    return found_target and signals_only


def mine(
    transactions, min_support: float, min_confidence: float, max_len: int, min_lift: float = 2.0
) -> list[Rule]:
    itemsets = frequent_itemsets(transactions, min_support, max_len)
    rules = association_rules(
        itemsets,
        len(transactions),
        min_confidence,
        consequent=lambda i: i.startswith(("bug=", "fp=")),
        antecedent_item=_observable,
    )
    rules = [r for r in rules if r.lift >= min_lift and _useful(r)]
    return prune_redundant(rules)


# ------------------------------------------------------------ đánh giá


def predict(rec: dict, rules: list[Rule], kinds: set[str], threshold: float) -> set[str]:
    """Đoán lỗi thật từ lỗi tầng luật báo, rồi áp luật khai phá thuộc các loại trong `kinds`."""
    pred = {f["bug_pattern"] for f in rec["findings"]}
    t = transaction(rec, with_labels=False)
    fired = [r for r in rules if rule_kind(r) in kinds and r.confidence >= threshold
             and r.matches(t)]  # fmt: skip
    pred |= {rule_bug(r) for r in fired if rule_kind(r) == "add"}
    pred -= {rule_bug(r) for r in fired if rule_kind(r) == "suppress"}
    return pred


def label_vocab(records) -> set[str]:
    """Các mã lỗi có nhãn đúng (bộ mutation cài được)."""
    return {b for r in records for b in r["labels"]}


def scores(records, predictions, vocab: set[str] | None = None) -> dict:
    """P/R/F1 trên tập mã có nhãn đúng; dự đoán ngoài `vocab` không chấm được nên bỏ qua."""
    tp = fp = fn = exact = 0
    for rec, pred in zip(records, predictions, strict=True):
        gold = set(rec["labels"])
        if vocab is not None:
            pred = pred & vocab
        tp += len(pred & gold)
        fp += len(pred - gold)
        fn += len(gold - pred)
        exact += gold <= pred
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {
        "precision": p,
        "recall": r,
        "f1": 2 * p * r / (p + r) if p + r else 0.0,
        "all_bugs_found": exact / len(records) if records else 0.0,
    }


VARIANTS = {
    "baseline": set(),
    "add": {"add"},
    "suppress": {"suppress"},
    "both": {"add", "suppress"},
}


def leave_one_problem_out(records, args) -> list[dict]:
    rows = []
    for pid in sorted({r["problem_id"] for r in records}):
        train = [r for r in records if r["problem_id"] != pid]
        test = [r for r in records if r["problem_id"] == pid]
        vocab = label_vocab(records)
        rules = mine([transaction(r, label_vocab=vocab) for r in train], args.min_support,
                     args.min_confidence, args.max_len)  # fmt: skip
        row = {"test_problem": pid, "n": len(test), "rules": len(rules)}
        for name, kinds in VARIANTS.items():
            preds = [predict(r, rules, kinds, args.apply_threshold) for r in test]
            row[name] = scores(test, preds, vocab)
        rows.append(row)
    return rows


def detection_table(records) -> list[dict]:
    """Tầng luật v0 so với nhãn đúng, theo từng mã lỗi."""
    rows = []
    for bug in sorted({b for r in records for b in r["labels"]}):
        have = [r for r in records if bug in r["labels"]]
        hit = sum(any(f["bug_pattern"] == bug for f in r["findings"]) for r in have)
        flagged = [r for r in records if any(f["bug_pattern"] == bug for f in r["findings"])]
        correct = sum(bug in r["labels"] for r in flagged)
        rows.append({
            "bug": bug, "n": len(have), "recall": hit / len(have),
            "precision": correct / len(flagged) if flagged else None,
            "verdicts": dict(Counter(r["verdict"] for r in have).most_common()),
        })  # fmt: skip
    return rows


# ------------------------------------------------------------ xuất kết quả


def _fmt_rule(r: Rule) -> str:
    rhs = f"lỗi thật {rule_bug(r)}" if rule_kind(r) == "add" else f"bỏ {rule_bug(r)}"
    return "{" + ", ".join(r.antecedent) + "} → " + rhs


def write_yaml(rules: list[Rule], path: Path, meta: dict) -> None:
    data = {
        "meta": meta,
        "rules": [
            {
                "id": f"MR{i:03d}",
                "kind": rule_kind(r),
                "if": list(r.antecedent),
                "then": rule_bug(r),
                "support": round(r.support, 4),
                "confidence": round(r.confidence, 4),
                "lift": round(r.lift, 2),
                "count": r.count,
            }
            for i, r in enumerate(rules, 1)
        ],
    }
    path.write_text(
        "# SINH TỰ ĐỘNG bởi backend/app/mining/mine.py, không sửa tay.\n"
        + yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )


def write_report(path: Path, records, rules, lopo, detection, meta) -> None:
    pct = lambda x: "–" if x is None else f"{x:.0%}"  # noqa: E731
    out = [
        "# Báo cáo khai phá luật chẩn đoán",
        "",
        "> Sinh tự động bởi `python -m backend.app.mining.mine`. Không sửa tay.",
        "",
        "## Dữ liệu",
        "",
        f"- {meta['records']} bài nộp giả lập từ {meta['problems']} bài tập "
        "(cài lỗi có chủ đích vào lời giải mẫu, `backend/app/mining/mutate.py`), "
        f"chấm bằng hệ v0. {meta['multi_bug']} bài mang 2 lỗi.",
        f"- Tham số: min_support={meta['min_support']}, "
        f"min_confidence={meta['min_confidence']}, độ dài tập mục tối đa={meta['max_len']}.",
        "- Verdict: "
        + ", ".join(f"{k} {v}" for k, v in Counter(r["verdict"] for r in records).most_common()),
        "",
        "## Tầng luật v0 so với nhãn đúng",
        "",
        "| Lỗi đã cài | Số bài | Recall | Precision | Verdict thường gặp |",
        "|---|---|---|---|---|",
    ]
    for d in detection:
        verdicts = ", ".join(f"{k} {v}" for k, v in d["verdicts"].items())
        out.append(f"| {d['bug']} | {d['n']} | {pct(d['recall'])} | {pct(d['precision'])} | "
                   f"{verdicts} |")  # fmt: skip
    out += [
        "",
        "Recall thấp: công cụ bỏ sót hoặc gọi sai tên lỗi. Precision thấp: công cụ báo cả các "
        "hệ quả của lỗi gốc. Hai loại luật khai phá dưới đây nhắm vào hai vấn đề này.",
        "",
        f"## Luật khai phá ({len(rules)} luật)",
        "",
    ]
    ids = {r: f"MR{i:03d}" for i, r in enumerate(rules, 1)}
    for kind, title in (
        ("add", "Luật bổ sung: đoán lỗi thật công cụ bỏ sót / gọi sai tên"),
        ("suppress", "Luật khử nhiễu: cảnh báo chỉ là hệ quả của lỗi gốc khác"),
    ):
        chosen = [r for r in rules if rule_kind(r) == kind]
        out += [
            f"### {title} ({len(chosen)} luật, top 15)",
            "",
            "| # | Luật | Support | Confidence | Lift |",
            "|---|---|---|---|---|",
        ]
        out += [
            f"| {ids[r]} | `{_fmt_rule(r)}` | {r.support:.3f} | {r.confidence:.2f} | {r.lift:.1f} |"
            for r in chosen[:15]
        ]
        out.append("")  # fmt: skip
    out += [
        "",
        "## Đánh giá leave-one-problem-out",
        "",
        "Khai phá luật trên các bài còn lại, kiểm tra trên bài để riêng (bài chưa thấy khi khai "
        f"phá). Áp dụng luật có confidence ≥ {meta['apply_threshold']}.",
        "",
        "Mỗi ô: precision / recall / F1 khi đoán tập lỗi thật của từng bài nộp, chỉ tính trên "
        "các mã lỗi có nhãn đúng (mã bộ mutation cài được).",
        "",
        "| Bài kiểm tra | Số bài nộp | Số luật | Chỉ tầng luật v0 | + luật bổ sung | "
        "+ luật khử nhiễu | + cả hai |",
        "|---|---|---|---|---|---|---|",
    ]
    cell = lambda s: f"{s['precision']:.2f} / {s['recall']:.2f} / {s['f1']:.2f}"  # noqa: E731
    for row in lopo:
        out.append(f"| {row['test_problem']} | {row['n']} | {row['rules']} | "
                   + " | ".join(cell(row[v]) for v in VARIANTS) + " |")  # fmt: skip
    avg = {v: sum(row[v]["f1"] for row in lopo) / len(lopo) for v in VARIANTS}
    out += ["", "F1 trung bình: " + ", ".join(f"{v} {avg[v]:.2f}" for v in VARIANTS) + "."]
    best = max(VARIANTS, key=avg.get)
    names = {"baseline": "chỉ tầng luật v0", "add": "thêm luật bổ sung",
             "suppress": "thêm luật khử nhiễu", "both": "thêm cả hai loại luật"}  # fmt: skip
    out += [
        "",
        "## Kết luận",
        "",
        f"- Cấu hình tốt nhất trên bài chưa thấy: **{names[best]}** (F1 trung bình "
        f"{avg['baseline']:.2f} → {avg[best]:.2f}).",
        "- Luật khử nhiễu tổng quát được vì mô tả quan hệ giữa các cảnh báo (lỗi gốc kéo theo "
        "cảnh báo hệ quả), không phụ thuộc bài tập cụ thể.",
        f"- Luật bổ sung {'cũng giúp ích' if avg['add'] > avg['baseline'] else 'làm giảm F1'} "
        f"({avg['baseline']:.2f} → {avg['add']:.2f}): với ít bài tập, chúng dễ học thuộc đặc "
        "điểm của từng bài. Chỉ nên đưa vào rule engine khi có thêm bài tập và log thật.",
    ]
    out += [
        "",
        "## Hạn chế",
        "",
        f"- Mới có {meta['problems']} bài tập và lỗi do máy cài, chưa phải log sinh viên thật: "
        "luật phản ánh cách hệ v0 phản ứng với từng loại lỗi hơn là thói quen của sinh viên.",
        "- Thêm bài tập (mục tiêu 10–15) và log thật thì chạy lại hai lệnh `generate`, `mine`.",
        "",
    ]
    path.write_text("\n".join(out), encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--input", type=Path, default=ROOT / "data/mined/mutants.jsonl")
    ap.add_argument("--rules-out", type=Path, default=ROOT / "knowledge/mined_rules.yaml")
    ap.add_argument("--report-out", type=Path, default=ROOT / "docs/mining_report.md")
    ap.add_argument("--min-support", type=float, default=0.03)
    ap.add_argument("--min-confidence", type=float, default=0.7)
    ap.add_argument("--max-len", type=int, default=4)
    ap.add_argument("--apply-threshold", type=float, default=0.8,
                    help="confidence tối thiểu để áp dụng luật khi đánh giá")  # fmt: skip
    args = ap.parse_args(argv)

    records = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines()]
    vocab = label_vocab(records)
    rules = mine([transaction(r, label_vocab=vocab) for r in records], args.min_support,
                 args.min_confidence, args.max_len)  # fmt: skip
    meta = {
        "source": str(args.input.relative_to(ROOT) if args.input.is_absolute() else args.input),
        "records": len(records),
        "problems": len({r["problem_id"] for r in records}),
        "multi_bug": sum(len(r["labels"]) > 1 for r in records),
        "min_support": args.min_support,
        "min_confidence": args.min_confidence,
        "max_len": args.max_len,
        "apply_threshold": args.apply_threshold,
    }
    lopo = leave_one_problem_out(records, args)
    write_yaml(rules, args.rules_out, {k: v for k, v in meta.items() if k != "apply_threshold"})
    write_report(args.report_out, records, rules, lopo, detection_table(records), meta)
    print(f"{len(rules)} luật -> {args.rules_out}\nBáo cáo -> {args.report_out}")
    for row in lopo:
        print(f"  {row['test_problem']}: F1 " + "  ".join(f"{v} {row[v]['f1']:.2f}"
                                                         for v in VARIANTS))  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
