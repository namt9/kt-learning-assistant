"""Apriori: tìm tập mục phổ biến rồi sinh luật kết hợp X -> y.

Tự cài (không dùng thư viện) để nhóm giải thích được từng bước trong báo cáo:

1. L1 = các mục có support >= min_support.
2. Lk = ghép các tập trong L(k-1) thành ứng viên kích thước k, bỏ ứng viên có tập con kích thước
   k-1 không phổ biến (tính chất Apriori), rồi đếm support trên dữ liệu.
3. Với mỗi tập phổ biến S và mỗi mục y thuộc S thoả `consequent(y)`, sinh luật S\\{y} -> y,
   giữ luật có confidence >= min_confidence.

support(X)       = số giao dịch chứa X / tổng số giao dịch
confidence(X->y) = support(X ∪ {y}) / support(X)
lift(X->y)       = confidence(X->y) / support({y})   (> 1: X làm y dễ xảy ra hơn bình thường)
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from itertools import combinations


@dataclass(frozen=True)
class Rule:
    antecedent: tuple[str, ...]
    consequent: str
    count: int  # số giao dịch chứa cả vế trái và vế phải
    support: float
    confidence: float
    lift: float

    def matches(self, transaction: frozenset[str]) -> bool:
        return set(self.antecedent) <= transaction


def frequent_itemsets(
    transactions: list[frozenset[str]], min_support: float, max_len: int = 4
) -> dict[frozenset[str], int]:
    n = len(transactions)
    min_count = max(1, int(min_support * n + 0.999999))  # làm tròn lên
    counts = Counter(item for t in transactions for item in t)
    level = {frozenset([i]): c for i, c in counts.items() if c >= min_count}
    result = dict(level)
    k = 2
    while level and k <= max_len:
        prev = list(level)
        candidates = set()
        for a, b in combinations(prev, 2):
            union = a | b
            if len(union) == k and all(frozenset(s) in level for s in combinations(union, k - 1)):
                candidates.add(union)
        counted = Counter()
        for t in transactions:
            for cand in candidates:
                if cand <= t:
                    counted[cand] += 1
        level = {c: v for c, v in counted.items() if v >= min_count}
        result.update(level)
        k += 1
    return result


def association_rules(
    itemsets: dict[frozenset[str], int],
    n_transactions: int,
    min_confidence: float,
    consequent: Callable[[str], bool] = lambda _: True,
    antecedent_item: Callable[[str], bool] = lambda _: True,
) -> list[Rule]:
    rules = []
    for items, count in itemsets.items():
        if len(items) < 2:
            continue
        for y in items:
            lhs = items - {y}
            if not consequent(y) or not all(antecedent_item(i) for i in lhs):
                continue
            conf = count / itemsets[lhs]
            if conf < min_confidence:
                continue
            p_y = itemsets[frozenset([y])] / n_transactions
            rules.append(
                Rule(tuple(sorted(lhs)), y, count, count / n_transactions, conf, conf / p_y)
            )
    rules.sort(key=lambda r: (-r.confidence, -r.lift, -r.count, len(r.antecedent)))
    return rules


def prune_redundant(rules: Iterable[Rule], min_improvement: float = 0.01) -> list[Rule]:
    """Bỏ luật mà một luật tổng quát hơn (vế trái là tập con, cùng vế phải) đã tốt bằng.

    Ví dụ đã có {verdict=TLE} -> bug=INFINITE_LOOP (conf 1.0) thì
    {verdict=TLE, feat=scanf} -> bug=INFINITE_LOOP không thêm thông tin gì.
    """
    rules = sorted(rules, key=lambda r: len(r.antecedent))
    kept: list[Rule] = []
    for r in rules:
        general = [
            g for g in kept
            if g.consequent == r.consequent and set(g.antecedent) < set(r.antecedent)
        ]  # fmt: skip
        if all(r.confidence >= g.confidence + min_improvement for g in general):
            kept.append(r)
    kept.sort(key=lambda r: (-r.confidence, -r.lift, -r.count, len(r.antecedent)))
    return kept
