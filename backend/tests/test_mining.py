"""Khai phá luật: Apriori, toán tử cài lỗi, giao dịch và đánh giá."""

import subprocess

import pytest

from backend.app.config import ROOT
from backend.app.mining.apriori import (
    Rule,
    association_rules,
    frequent_itemsets,
    prune_redundant,
)
from backend.app.mining.mine import code_features, mine, predict, scores, transaction
from backend.app.mining.mutate import OPERATORS, pair_mutants, single_mutants

SOLUTIONS = sorted((ROOT / "data" / "problems").glob("*/solution.c"))

# Ví dụ kinh điển trong giáo trình khai phá dữ liệu
BASKETS = [frozenset(t) for t in (
    {"sua", "banh_mi"}, {"banh_mi", "ta", "bia", "trung"}, {"sua", "ta", "bia", "nuoc_ngot"},
    {"banh_mi", "sua", "ta", "bia"}, {"banh_mi", "sua", "ta", "nuoc_ngot"},
)]  # fmt: skip


def test_frequent_itemsets_and_rules():
    freq = frequent_itemsets(BASKETS, min_support=0.6)
    assert freq[frozenset({"ta", "bia"})] == 3
    assert frozenset({"trung"}) not in freq  # support 0.2 < 0.6
    # mọi tập con của tập phổ biến đều phổ biến (tính chất Apriori)
    assert all(frozenset(s) in freq for f in freq for s in [f - {i} for i in f] if s)
    rules = association_rules(freq, len(BASKETS), min_confidence=0.9)
    bia_ta = next(r for r in rules if r.antecedent == ("bia",) and r.consequent == "ta")
    assert bia_ta.confidence == 1.0 and bia_ta.support == pytest.approx(0.6)
    assert bia_ta.lift == pytest.approx(1.25)  # 1.0 / P(ta) = 1 / 0.8


def test_prune_redundant_keeps_only_improving_rules():
    general = Rule(("a",), "bug=X", 10, 0.1, 0.9, 2.0)
    same = Rule(("a", "b"), "bug=X", 8, 0.08, 0.9, 2.0)
    better = Rule(("a", "c"), "bug=X", 5, 0.05, 1.0, 2.2)
    assert prune_redundant([same, general, better]) == [better, general]


@pytest.mark.parametrize("path", SOLUTIONS, ids=lambda p: p.parent.name)
def test_mutants_change_code_and_keep_others_compilable(path, tmp_path):
    src = path.read_text()
    mutants = single_mutants(src)
    assert mutants and all(m.source != src for m in mutants)
    assert len({m.source for m in mutants}) == len(mutants)
    for i, m in enumerate(mutants):
        f = tmp_path / f"m{i}.c"
        f.write_text(m.source)
        ok = subprocess.run(["gcc", "-std=c11", "-fsyntax-only", str(f)],
                            capture_output=True).returncode == 0  # fmt: skip
        breaks_compile = m.labels[0] in {"SYNTAX_ERROR", "UNDECLARED_ID"}
        assert ok != breaks_compile, (m.ops, m.source)


def test_operator_examples():
    p002 = (ROOT / "data/problems/P002_mang_dong/solution.c").read_text()
    by_op = {m.ops[0].split("@")[0]: m for m in single_mutants(p002)}
    assert "free(a);" not in by_op["drop_free"].source
    assert by_op["double_free"].source.count("free(a);") == 2
    lines = by_op["early_free"].source.splitlines()
    assert lines.index("    free(a);") < next(i for i, ln in enumerate(lines) if "printf" in ln)
    assert "malloc((n - 1) *" in by_op["short_alloc"].source
    p001 = (ROOT / "data/problems/P001_tong_mang/solution.c").read_text()
    renamed = next(m for m in single_mutants(p001) if m.ops[0].startswith("rename_use"))
    assert 'printf("%lld\\n", Sum);' in renamed.source  # không đổi nhầm "\n" trong chuỗi
    assert {op.bug for op in OPERATORS} >= {"SCANF_MISSING_AMP", "MEM_LEAK", "OFF_BY_ONE"}


def test_pair_mutants_have_two_distinct_bugs():
    src = SOLUTIONS[1].read_text()
    pairs = pair_mutants(src, 15, seed=1)
    assert len(pairs) == 15
    assert all(len(set(m.labels)) == 2 and len(m.ops) == 2 for m in pairs)
    assert pairs == pair_mutants(src, 15, seed=1)  # cùng seed thì tái lập được


def record(verdict, found, labels, source="int main(void){int *p=malloc(4);return 0;}"):
    return {"problem_id": "P", "concepts": ["mang"], "verdict": verdict, "labels": labels,
            "findings": [{"bug_pattern": b} for b in found], "source": source}  # fmt: skip


def test_transaction_items():
    t = transaction(record("WA", [], ["MEM_LEAK"]))
    assert {"verdict=WA", "found=NONE", "feat=malloc", "feat=malloc_no_free",
            "concept=mang", "bug=MEM_LEAK"} <= t  # fmt: skip
    assert not any(i.startswith("bug=") for i in transaction(record("WA", [], ["X"]), False))
    assert "free" not in code_features('int main(void){ printf("free(p)"); }')


def test_mined_rules_recover_bug_tools_miss():
    # công cụ không báo gì khi TLE, nhưng lỗi thật luôn là vòng lặp vô hạn
    data = [record("TLE", [], ["INFINITE_LOOP"]) for _ in range(5)]
    data += [record("WA", ["UNINIT_VAR"], ["UNINIT_VAR"]) for _ in range(5)]
    rules = mine([transaction(r) for r in data], 0.2, 0.9, 3)
    assert any(r.antecedent == ("verdict=TLE",) and r.consequent == "bug=INFINITE_LOOP"
               for r in rules)  # fmt: skip
    test = [record("TLE", [], ["INFINITE_LOOP"])]
    assert predict(test[0], rules, set(), threshold=0.8) == set()
    assert predict(test[0], rules, {"add"}, threshold=0.8) == {"INFINITE_LOOP"}
    s = scores(test, [{"INFINITE_LOOP", "MEM_LEAK"}])
    assert s["recall"] == 1.0 and s["precision"] == 0.5 and s["all_bugs_found"] == 1.0


def test_suppress_rules_remove_cascading_warnings():
    # thiếu & làm chương trình crash: công cụ báo thêm NULL_DEREF nhưng gốc là SCANF_MISSING_AMP
    data = [record("RE", ["SCANF_MISSING_AMP", "NULL_DEREF"], ["SCANF_MISSING_AMP"])] * 5
    data += [record("RE", ["NULL_DEREF"], ["NULL_DEREF"])] * 5
    vocab = {"SCANF_MISSING_AMP", "NULL_DEREF"}
    rules = mine([transaction(r, label_vocab=vocab) for r in data], 0.2, 0.9, 3, min_lift=1.5)
    sup = [r for r in rules if r.consequent == "fp=NULL_DEREF"]
    assert sup and all("found=NULL_DEREF" in r.antecedent for r in sup)
    assert any("found=SCANF_MISSING_AMP" in r.antecedent for r in sup)
    both = record("RE", ["SCANF_MISSING_AMP", "NULL_DEREF"], [])
    assert predict(both, rules, {"suppress"}, 0.8) == {"SCANF_MISSING_AMP"}
    alone = record("RE", ["NULL_DEREF"], [])
    assert predict(alone, rules, {"suppress"}, 0.8) == {"NULL_DEREF"}  # NULL_DEREF thật: giữ

    # mã không bao giờ có nhãn (không cài được) thì không được học thành "luôn báo sai"
    t = transaction(record("RE", ["CONST_CONDITION"], ["NULL_DEREF"]), label_vocab=vocab)
    assert "fp=CONST_CONDITION" not in t
