"""Luật tự viết (custom rules) cho các lỗi mà công cụ chuẩn hay bỏ sót.

Bản v0 dùng heuristic trên mã nguồn đã bỏ comment/chuỗi, không cần parser đầy đủ.
Mỗi luật trả về Finding với confidence < 1 để phân biệt với kết quả chắc chắn của công cụ.
(v1 có thể thay bằng phân tích AST qua tree-sitter/pycparser.)
"""

from __future__ import annotations

import re
from collections.abc import Callable

from ..schemas import Finding

Rule = Callable[[str, str], list[Finding]]  # (mã gốc, mã đã làm sạch) -> findings


def strip_comments_and_strings(src: str) -> str:
    """Thay comment, chuỗi và ký tự literal bằng khoảng trắng, giữ nguyên số dòng/cột."""

    def blank(m: re.Match) -> str:
        s = m.group(0)
        body = re.sub(r"[^\n]", " ", s)
        if s[0] in "\"'":  # giữ dấu nháy để vẫn nhận ra đây là literal
            return s[0] + body[1:-1] + s[0]
        return body

    pattern = r"//[^\n]*|/\*.*?\*/|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'"
    return re.sub(pattern, blank, src, flags=re.S)


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _split_args(s: str) -> list[str]:
    """Tách danh sách đối số theo dấu phẩy ở mức ngoài cùng."""
    args, depth, cur = [], 0, []
    for ch in s:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            args.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        args.append("".join(cur).strip())
    return args


def _call_args(text: str, open_paren: int) -> tuple[str, int] | None:
    """Trả về (nội dung trong ngoặc, vị trí ngoặc đóng) bắt đầu từ ngoặc mở."""
    depth = 0
    for i in range(open_paren, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren + 1 : i], i
    return None


# ------------------------------------------------------------------ các luật


_DECL = re.compile(
    r"\b(?P<type>(?:unsigned\s+|signed\s+|long\s+|short\s+)*(?:int|long|short|char|float|double|"
    r"size_t|bool))\s+(?P<rest>[^;(){}]+);"
)


def _declared_types(clean: str) -> dict[str, str]:
    """Bảng tên biến -> kiểu (chỉ cho khai báo đơn giản, đủ dùng cho heuristic)."""
    types: dict[str, str] = {}
    for m in _DECL.finditer(clean):
        t = re.sub(r"\s+", " ", m["type"])
        for part in _split_args(m["rest"]):
            name = re.match(r"\s*(\**)\s*([A-Za-z_]\w*)\s*(\[)?", part)
            if not name:
                continue
            kind = t
            if name.group(1):
                kind += "*"
            if name.group(3):
                kind += "[]"
            types[name.group(2)] = kind
    return types


def rule_scanf_missing_amp(src: str, clean: str) -> list[Finding]:
    findings = []
    types = _declared_types(clean)
    for m in re.finditer(r"\bscanf\s*\(", clean):
        got = _call_args(src, m.end() - 1)
        if not got:
            continue
        args = _split_args(got[0])
        if not args or not args[0].startswith('"'):
            continue
        fmt = args[0].strip('"')
        fmt = fmt.replace("%%", "")
        found = re.findall(r"%(\*?)\d*[hlLjzt]*([diouxXeEfgGaAcs\[n])", fmt)
        convs = [c for star, c in found if not star]  # %*d: đọc rồi bỏ, không cần đối số
        for conv, arg in zip(convs, args[1:], strict=False):
            if arg.startswith("&") or conv in ("s", "["):
                continue
            base = re.match(r"[A-Za-z_]\w*", arg)
            if not base:
                continue
            t = types.get(base.group(0), "")
            if "*" in t or ("[]" in t and "[" not in arg):
                continue  # con trỏ hoặc tên mảng: đã là địa chỉ
            findings.append(
                Finding(
                    bug_pattern="SCANF_MISSING_AMP",
                    source="custom_rule",
                    line=_line_of(clean, m.start()),
                    message=f'scanf đọc "%{conv}" vào "{arg}" nhưng thiếu "&"',
                    confidence=0.85 if t else 0.6,
                )
            )
    return findings


def rule_assign_in_condition(src: str, clean: str) -> list[Finding]:
    findings = []
    for m in re.finditer(r"\b(if|while)\s*\(", clean):
        got = _call_args(clean, m.end() - 1)
        if not got:
            continue
        cond = got[0]
        # a = b nhưng không phải ==, !=, <=, >=, +=, ...
        if re.search(r"(?<![=!<>+\-*/%&|^])=(?!=)", cond) and not re.search(r"\(\s*\(", cond):
            findings.append(
                Finding(
                    bug_pattern="ASSIGN_IN_COND",
                    source="custom_rule",
                    line=_line_of(clean, m.start()),
                    message=f"Điều kiện của {m.group(1)} có phép gán '=': ({cond.strip()})",
                    confidence=0.8,
                )
            )
    return findings


def rule_stray_semicolon(src: str, clean: str) -> list[Finding]:
    findings = []
    for m in re.finditer(r"\b(if|for|while)\s*\(", clean):
        got = _call_args(clean, m.end() - 1)
        if not got:
            continue
        rest = clean[got[1] + 1 :]
        if re.match(r"[ \t]*;", rest):
            # while(...); ngay sau "}" là do-while hợp lệ
            before = clean[: m.start()].rstrip()
            if m.group(1) == "while" and before.endswith("}"):
                continue
            findings.append(
                Finding(
                    bug_pattern="STRAY_SEMICOLON",
                    source="custom_rule",
                    line=_line_of(clean, m.start()),
                    message=f"Dấu ';' ngay sau {m.group(1)}(...) làm thân câu lệnh rỗng",
                    confidence=0.85,
                )
            )
    return findings


def rule_off_by_one(src: str, clean: str) -> list[Finding]:
    findings = []
    arrays = {
        name: size.strip()
        for name, size in re.findall(r"\b[A-Za-z_]\w*\s+([A-Za-z_]\w*)\s*\[\s*([^\]]+)\]", clean)
    }
    loop = re.compile(
        r"\bfor\s*\(\s*(?:[A-Za-z_]\w*\s+)?(?P<i>[A-Za-z_]\w*)\s*=\s*0\s*;"
        r"\s*(?P=i)\s*<=\s*(?P<bound>[^;]+);"
    )
    for m in loop.finditer(clean):
        i, bound = m["i"], m["bound"].strip()
        if re.search(r"-\s*1\s*$", bound):
            continue  # i <= n - 1 là đúng
        body = clean[m.end() : m.end() + 600]
        indexed = [a for a in re.findall(rf"([A-Za-z_]\w*)\s*\[\s*{re.escape(i)}\s*\]", body)]
        if not indexed:
            continue
        same_size = any(arrays.get(a) == bound for a in indexed)
        findings.append(
            Finding(
                bug_pattern="OFF_BY_ONE",
                source="custom_rule",
                line=_line_of(clean, m.start()),
                message=f"Vòng lặp {i} = 0 .. {i} <= {bound} truy cập {indexed[0]}[{i}]: "
                f"có thể vượt quá phần tử cuối",
                confidence=0.85 if same_size else 0.6,
            )
        )
    return findings


def rule_int_division(src: str, clean: str) -> list[Finding]:
    findings = []
    types = _declared_types(clean)

    def is_int(tok: str) -> bool:
        tok = tok.strip()
        if re.fullmatch(r"\d+", tok):
            return True
        t = types.get(tok)
        return bool(t) and not any(k in t for k in ("float", "double", "*", "[]"))

    target = re.compile(
        r"(?:\b(?:float|double)\s+|\b(?P<var>[A-Za-z_]\w*)\s*)=\s*(?P<expr>[^;=][^;]*);"
    )
    for m in target.finditer(clean):
        var = m["var"]
        if var and "float" not in types.get(var, "") and "double" not in types.get(var, ""):
            continue
        expr = m["expr"]
        if "(double)" in expr.replace(" ", "") or "(float)" in expr.replace(" ", ""):
            continue
        operand = r"([A-Za-z_]\w*|\d+(?:\.\d*)?(?:[eE][+-]?\d+)?[fF]?)"  # 2.0 / 1e3 là số thực
        for a, b in re.findall(rf"{operand}\s*/\s*{operand}", expr):
            if is_int(a) and is_int(b):
                findings.append(
                    Finding(
                        bug_pattern="INT_DIVISION",
                        source="custom_rule",
                        line=_line_of(clean, m.start()),
                        message=f"Phép chia {a} / {b} giữa hai số nguyên rồi gán cho số thực",
                        confidence=0.75,
                    )
                )
                break
    return findings


def rule_malloc_without_free(src: str, clean: str) -> list[Finding]:
    allocs = list(re.finditer(r"\b(malloc|calloc|realloc|strdup)\s*\(|\bnew\b", clean))
    frees = re.findall(r"\bfree\s*\(|\bdelete\b", clean)
    if allocs and not frees:
        return [
            Finding(
                bug_pattern="MEM_LEAK",
                source="custom_rule",
                line=_line_of(clean, allocs[0].start()),
                message=f"Có {len(allocs)} lần cấp phát động nhưng không có free/delete nào",
                confidence=0.6,
            )
        ]
    return []


RULES: list[Rule] = [
    rule_scanf_missing_amp,
    rule_assign_in_condition,
    rule_stray_semicolon,
    rule_off_by_one,
    rule_int_division,
    rule_malloc_without_free,
]


def run_custom_rules(src: str) -> list[Finding]:
    clean = strip_comments_and_strings(src)
    out: list[Finding] = []
    for rule in RULES:
        out.extend(rule(src, clean))
    return out
