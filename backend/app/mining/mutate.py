"""Sinh bài làm có lỗi bằng cách cài lỗi có chủ đích (mutation) vào lời giải mẫu.

Mỗi toán tử mô phỏng một lỗi sinh viên hay mắc và biết chắc mã Bug Pattern của lỗi đó, nên mỗi
biến thể có nhãn đúng (ground truth). Dùng cho hai việc:

- sinh log có nhãn để khai phá luật chẩn đoán khi chưa có log thật;
- làm benchmark đo độ chính xác của tầng luật / LLM (tuần 4).

Toán tử làm việc trên văn bản (regex theo dòng) nên chỉ hợp với code định dạng gọn như lời giải
mẫu; biến thể không đổi gì so với bản gốc sẽ bị bỏ.
"""

from __future__ import annotations

import random
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from ..rules.custom import strip_comments_and_strings


@dataclass(frozen=True)
class Mutant:
    source: str
    labels: tuple[str, ...]  # mã Bug Pattern đã cài
    ops: tuple[str, ...]  # toán tử đã dùng kèm dòng, ví dụ "drop_amp@6"


@dataclass(frozen=True)
class Operator:
    name: str
    bug: str
    apply: Callable[[str], Iterator[tuple[str, int]]]  # sinh (code mới, dòng bị sửa)


def _line_of(src: str, pos: int) -> int:
    return src.count("\n", 0, pos) + 1


def _replace_each(pattern: str, repl: Callable[[re.Match], str], flags=0):
    """Toán tử thay lần lượt TỪNG chỗ khớp (mỗi chỗ một biến thể)."""

    def apply(src: str):
        for m in re.finditer(pattern, src, flags):
            new = src[: m.start()] + repl(m) + src[m.end() :]
            if new != src:
                yield new, _line_of(src, m.start())

    return apply


def _lines_matching(pattern: str, edit: Callable[[list[str], int], list[str] | None]):
    """Toán tử sửa theo dòng: `edit(lines, i)` trả về danh sách dòng mới hoặc None."""

    def apply(src: str):
        lines = src.splitlines()
        for i, line in enumerate(lines):
            if re.search(pattern, line):
                new = edit(list(lines), i)
                if new is not None:
                    yield "\n".join(new) + "\n", i + 1

    return apply


# ------------------------------------------------------------ từng toán tử


def _drop_amp(src: str):
    """scanf("%d", &n) -> scanf("%d", n): bỏ từng dấu & trong lời gọi scanf."""
    for call in re.finditer(r"scanf\s*\([^;]*\)", src):
        for amp in re.finditer(r"&(?=\s*\w)", call.group()):
            pos = call.start() + amp.start()
            yield src[:pos] + src[pos + 1 :], _line_of(src, pos)


def _remove_line(lines, i):
    del lines[i]
    return lines


def _duplicate_line(lines, i):
    lines.insert(i + 1, lines[i])
    return lines


def _early_free(lines, i):
    """Chuyển free(p) lên ngay sau dòng đầu tiên ghi vào p -> dùng con trỏ đã giải phóng."""
    var = re.search(r"free\s*\(\s*(\w+)\s*\)", lines[i]).group(1)
    first_use = next(
        (j for j, ln in enumerate(lines) if j != i and re.search(rf"\b{var}\s*\[", ln)), None
    )
    if first_use is None or first_use > i:
        return None
    stmt = lines.pop(i)
    indent = re.match(r"\s*", lines[first_use]).group()
    lines.insert(first_use + 1, indent + stmt.strip())
    return lines


def _drop_braces(lines, i):
    """for (...) { a; b; } -> for (...) a; b;  (chỉ còn câu đầu nằm trong vòng lặp)."""
    indent = re.match(r"\s*", lines[i]).group()
    close = next((j for j in range(i + 1, len(lines)) if lines[j] == indent + "}"), None)
    if close is None or close - i < 3:  # thân vòng lặp phải có ít nhất 2 câu lệnh
        return None
    if re.match(r"\s*(?:int|long|double|float|char|unsigned)\b", lines[i + 1]):
        return None  # khai báo không được làm thân vòng lặp -> lỗi cú pháp, không phải thiếu {}
    lines[i] = lines[i].rstrip()[:-1].rstrip()
    del lines[close]
    return lines


def _drop_semicolon(lines, i):
    lines[i] = lines[i].rstrip()[:-1]
    return lines


def _rename_use(src: str):
    """Gõ sai tên biến ở chỗ dùng (không phải chỗ khai báo) -> biến chưa khai báo."""
    code = strip_comments_and_strings(src)  # cùng vị trí với src, nhưng không khớp nhầm "\n"
    for var in ("sum", "avg", "n"):
        decl = re.search(rf"\b(?:long long|int|double)\s+(?:[^;]*?[\s,])?{var}\b", code)
        if not decl:
            continue
        uses = [m for m in re.finditer(rf"\b{var}\b", code) if m.start() > decl.end()]
        if uses:
            m = uses[-1]
            yield src[: m.start()] + var.capitalize() + src[m.end() :], _line_of(src, m.start())
            return


OPERATORS: list[Operator] = [
    Operator("drop_amp", "SCANF_MISSING_AMP", _drop_amp),
    Operator(
        "drop_init",
        "UNINIT_VAR",
        _replace_each(r"(\b(?:sum|s|total)\s*)=\s*0(?=\s*[,;])", lambda m: m.group(1).rstrip()),
    ),
    Operator(
        "lt_to_le",
        "OFF_BY_ONE",
        _replace_each(r"(\bi\s*)<(\s*n\s*;)", lambda m: f"{m.group(1)}<={m.group(2)}"),
    ),
    Operator(
        "start_at_n",
        "OFF_BY_ONE",
        _replace_each(r"(\bi\s*=\s*n)\s*-\s*1\b", lambda m: m.group(1)),
    ),
    Operator(
        "ge_to_gt",
        "OFF_BY_ONE",
        _replace_each(r"(\bi\s*)>=(\s*0\s*;)", lambda m: f"{m.group(1)}>{m.group(2)}"),
    ),
    Operator(
        "drop_increment",
        "INFINITE_LOOP",
        _replace_each(
            r"(for\s*\([^;]*;[^;]*;)\s*\w+\s*(?:\+\+|--)\s*\)", lambda m: m.group(1) + ")"
        ),
    ),
    Operator("drop_free", "MEM_LEAK", _lines_matching(r"^\s*free\s*\(", _remove_line)),
    Operator("double_free", "DOUBLE_FREE", _lines_matching(r"^\s*free\s*\(", _duplicate_line)),
    Operator("early_free", "DANGLING_PTR", _lines_matching(r"^\s*free\s*\(", _early_free)),
    Operator(
        "short_alloc",
        "ARRAY_OOB",
        _replace_each(r"malloc\s*\(\s*n\s*\*", lambda m: "malloc((n - 1) *"),
    ),  # fmt: skip
    Operator("drop_cast", "INT_DIVISION", _replace_each(r"\((?:double|float)\)\s*", lambda m: "")),
    Operator(
        "eq_to_assign",
        "ASSIGN_IN_COND",
        _replace_each(
            r"(\bif\s*\(\s*\w+\s*)==(\s*\w+\s*\))", lambda m: f"{m.group(1)}={m.group(2)}"
        ),
    ),
    Operator(
        "stray_semicolon",
        "STRAY_SEMICOLON",
        _replace_each(r"(for\s*\([^)]*\))(\s*\{)", lambda m: m.group(1) + ";" + m.group(2)),
    ),
    Operator(
        "drop_braces", "MISSING_BRACES", _lines_matching(r"^\s*for\s*\(.*\)\s*\{\s*$", _drop_braces)
    ),  # fmt: skip
    Operator(
        "wrong_format",
        "FORMAT_MISMATCH",
        _replace_each(
            r'(printf\s*\(\s*")([^"]*?)%(?:lld|\.2f)', lambda m: f"{m.group(1)}{m.group(2)}%d"
        ),
    ),
    Operator(
        "narrow_type",
        "INT_OVERFLOW",
        _replace_each(r"\blong long(\s+sum\b)", lambda m: "int" + m.group(1)),
    ),
    Operator(
        "drop_semicolon", "SYNTAX_ERROR", _lines_matching(r"^\s*\w+\s*\+=.*;\s*$", _drop_semicolon)
    ),  # fmt: skip
    Operator("rename_use", "UNDECLARED_ID", _rename_use),
]

# Lỗi biên dịch che mất mọi lỗi khác, nên không ghép chúng với toán tử khác
_COMPILE_BREAKING = {"SYNTAX_ERROR", "UNDECLARED_ID"}


def single_mutants(src: str) -> list[Mutant]:
    out = []
    for op in OPERATORS:
        for new, line in op.apply(src):
            out.append(Mutant(new, (op.bug,), (f"{op.name}@{line}",)))
    return out


def pair_mutants(src: str, n: int, seed: int = 0) -> list[Mutant]:
    """Biến thể mang 2 lỗi khác loại, để có dữ liệu về lỗi xuất hiện cùng nhau."""
    rng = random.Random(seed)
    singles = [m for m in single_mutants(src) if m.labels[0] not in _COMPILE_BREAKING]
    ops = [op for op in OPERATORS if op.bug not in _COMPILE_BREAKING]
    seen, out = set(), []
    for _ in range(n * 20):
        if len(out) == n or not singles:
            break
        first = rng.choice(singles)
        op = rng.choice(ops)
        if op.bug == first.labels[0]:
            continue
        options = list(op.apply(first.source))
        if not options:
            continue
        new, line = rng.choice(options)
        if new in seen:
            continue
        seen.add(new)
        out.append(Mutant(new, first.labels + (op.bug,), first.ops + (f"{op.name}@{line}",)))
    return out
