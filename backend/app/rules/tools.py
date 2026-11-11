"""Chuyển đầu ra của gcc, cppcheck, AddressSanitizer/UBSan thành Finding (mã Bug Pattern)."""

from __future__ import annotations

import re

from ..schemas import Finding

SRC = r"main\.(?:c|cpp)"

# ------------------------------------------------------------------ gcc / g++

_GCC_LINE = re.compile(
    rf"^(?:.*/)?{SRC}:(?P<line>\d+):(?P<col>\d+):\s*(?P<kind>warning|error|fatal error):\s*"
    r"(?P<msg>.*?)(?:\s*\[(?P<flag>-W[\w=+-]+|-fpermissive)\])?$"
)

_GCC_FLAG_MAP = {
    "-Wuninitialized": "UNINIT_VAR",
    "-Wmaybe-uninitialized": "UNINIT_VAR",
    "-Wunused-variable": "UNUSED_VAR",
    "-Wunused-but-set-variable": "UNUSED_VAR",
    "-Wreturn-type": "MISSING_RETURN",
    "-Wreturn-local-addr": "DANGLING_PTR",
    "-Wuse-after-free": "DANGLING_PTR",
    "-Wdangling-pointer": "DANGLING_PTR",
    "-Warray-bounds": "ARRAY_OOB",
    "-Wstringop-overflow": "ARRAY_OOB",
    "-Wempty-body": "STRAY_SEMICOLON",
    "-Wdiv-by-zero": "DIV_BY_ZERO",
    "-Woverflow": "INT_OVERFLOW",
    "-Wincompatible-pointer-types": "TYPE_MISMATCH",
    "-Wint-conversion": "TYPE_MISMATCH",
    "-Wimplicit-function-declaration": "UNDECLARED_ID",
}

# Cảnh báo chỉ mang tính phong cách, không đưa thành lỗi
_GCC_IGNORE = {"-Wunused-result", "-Wunused-parameter", "-Wsign-compare", "-Wunused-function"}


def _classify_gcc(kind: str, msg: str, flag: str | None) -> str:
    m = msg.lower()
    if flag == "-Wparentheses" and "assignment" in m:
        return "ASSIGN_IN_COND"
    if flag and flag.startswith("-Wformat"):
        # scanf("%d", x) với x là int -> "expects argument of type 'int *', but ... has type 'int'"
        if "scanf" in m or re.search(r"expects argument of type '[^']*\*'.*has type '[^'*]*'$", m):
            return "SCANF_MISSING_AMP"
        return "FORMAT_MISMATCH"
    if flag in _GCC_FLAG_MAP:
        return _GCC_FLAG_MAP[flag]
    if "undeclared" in m or "was not declared" in m or "implicit declaration" in m:
        return "UNDECLARED_ID"
    if "incompatible type" in m or "cannot convert" in m or "invalid conversion" in m:
        return "TYPE_MISMATCH"
    if "no return statement" in m or "control reaches end of non-void" in m:
        return "MISSING_RETURN"
    if kind != "warning" and (
        m.startswith("expected") or "before" in m or "stray" in m or "missing terminating" in m
    ):
        return "SYNTAX_ERROR"
    return "UNCLASSIFIED"


def parse_gcc(output: str) -> list[Finding]:
    findings = []
    for raw in output.splitlines():
        mt = _GCC_LINE.match(raw.strip())
        if not mt:
            continue
        flag = mt["flag"]
        if flag in _GCC_IGNORE:
            continue
        code = _classify_gcc(mt["kind"], mt["msg"], flag)
        findings.append(
            Finding(
                bug_pattern=code,
                source="gcc",
                line=int(mt["line"]),
                message=f"{mt['kind']}: {mt['msg']}" + (f" [{flag}]" if flag else ""),
                confidence=1.0 if mt["kind"] != "warning" else 0.9,
            )
        )
    return findings


# ------------------------------------------------------------------ cppcheck

CPPCHECK_TEMPLATE = "{line}|{severity}|{id}|{message}"

_CPPCHECK_MAP = {
    "uninitvar": "UNINIT_VAR",
    "uninitdata": "UNINIT_VAR",
    "uninitMemberVar": "UNINIT_VAR",
    "unusedVariable": "UNUSED_VAR",
    "unreadVariable": "UNUSED_VAR",
    "arrayIndexOutOfBounds": "ARRAY_OOB",
    "arrayIndexOutOfBoundsCond": "ARRAY_OOB",
    "bufferAccessOutOfBounds": "ARRAY_OOB",
    "negativeIndex": "ARRAY_OOB",
    "outOfBounds": "ARRAY_OOB",
    "nullPointer": "NULL_DEREF",
    "nullPointerRedundantCheck": "NULL_DEREF",
    "nullPointerArithmetic": "NULL_DEREF",
    "memleak": "MEM_LEAK",
    "memleakOnRealloc": "MEM_LEAK",
    "leakReturnValNotUsed": "MEM_LEAK",
    "leakNoVarFunctionCall": "MEM_LEAK",
    "doubleFree": "DOUBLE_FREE",
    "deallocret": "DANGLING_PTR",
    "deallocuse": "DANGLING_PTR",
    "returnDanglingLifetime": "DANGLING_PTR",
    "danglingLifetime": "DANGLING_PTR",
    "autoVariables": "DANGLING_PTR",
    "returnLocalVariable": "DANGLING_PTR",
    "missingReturn": "MISSING_RETURN",
    "zerodiv": "DIV_BY_ZERO",
    "zerodivcond": "DIV_BY_ZERO",
    "integerOverflow": "INT_OVERFLOW",
}

# Mã lỗi cppcheck đổi tên theo phiên bản (vd. uninitvar -> legacyUninitvar),
# nên khi không có trong bảng thì đoán theo họ mã lỗi.
_CPPCHECK_FAMILIES = [
    ("uninit", "UNINIT_VAR"),
    ("nullpointer", "NULL_DEREF"),
    ("memleak", "MEM_LEAK"),
    ("leak", "MEM_LEAK"),
    ("outofbounds", "ARRAY_OOB"),
    ("doublefree", "DOUBLE_FREE"),
    ("dangling", "DANGLING_PTR"),
    ("zerodiv", "DIV_BY_ZERO"),
]


def _cppcheck_family(cid: str) -> str:
    low = cid.lower()
    return next((code for key, code in _CPPCHECK_FAMILIES if key in low), "UNCLASSIFIED")


_CPPCHECK_IGNORE = {"missingIncludeSystem", "checkersReport", "normalCheckLevelMaxBranches"}


def parse_cppcheck(output: str) -> list[Finding]:
    findings = []
    for raw in output.splitlines():
        parts = raw.strip().split("|", 3)
        if len(parts) != 4 or not parts[0].isdigit():
            continue
        line, severity, cid, msg = parts
        if cid in _CPPCHECK_IGNORE or severity == "information":
            continue
        if cid.startswith("invalidScanfArgType"):
            code = "SCANF_MISSING_AMP"
        elif cid.startswith(("invalidPrintfArgType", "wrongPrintfScanfArgNum")):
            code = "FORMAT_MISMATCH"
        else:
            code = _CPPCHECK_MAP.get(cid) or _cppcheck_family(cid)
        findings.append(
            Finding(
                bug_pattern=code,
                source="cppcheck",
                line=int(line) or None,
                message=f"{severity}: {msg} [{cid}]",
                confidence=0.9 if severity == "error" else 0.75,
            )
        )
    return findings


# ------------------------------------------------------------------ ASan / UBSan / LSan

_ASAN_MAP = [
    ("heap-buffer-overflow", "ARRAY_OOB"),
    ("stack-buffer-overflow", "ARRAY_OOB"),
    ("global-buffer-overflow", "ARRAY_OOB"),
    ("stack-buffer-underflow", "ARRAY_OOB"),
    ("heap-use-after-free", "DANGLING_PTR"),
    ("stack-use-after-return", "DANGLING_PTR"),
    ("stack-use-after-scope", "DANGLING_PTR"),
    ("attempting double-free", "DOUBLE_FREE"),
    ("attempting free on address which was not malloc", "DOUBLE_FREE"),
    ("stack-overflow", "INFINITE_LOOP"),  # đệ quy không dừng
]

_UBSAN_MAP = [
    ("signed integer overflow", "INT_OVERFLOW"),
    ("division by zero", "DIV_BY_ZERO"),
    ("out of bounds", "ARRAY_OOB"),
    ("null pointer", "NULL_DEREF"),
    ("misaligned address", "NULL_DEREF"),
    ("shift exponent", "INT_OVERFLOW"),
]

_FRAME_IN_SRC = re.compile(rf"#\d+ .*?{SRC}:(\d+)")
_UBSAN_LINE = re.compile(rf"{SRC}:(\d+):\d+: runtime error: (.*)")
_ASAN_ERROR = re.compile(r"ERROR: (AddressSanitizer|LeakSanitizer): (.*)")


def _first_src_line(text: str) -> int | None:
    m = _FRAME_IN_SRC.search(text)
    return int(m.group(1)) if m else None


def parse_sanitizer(stderr: str) -> list[Finding]:
    findings: list[Finding] = []
    for m in _UBSAN_LINE.finditer(stderr):
        line, msg = int(m.group(1)), m.group(2).strip()
        code = next((c for k, c in _UBSAN_MAP if k in msg), "UNCLASSIFIED")
        findings.append(Finding(bug_pattern=code, source="ubsan", line=line, message=msg))

    for m in _ASAN_ERROR.finditer(stderr):
        tool, msg = m.group(1), m.group(2).strip()
        after = stderr[m.end() :]
        if tool == "LeakSanitizer":
            code = "MEM_LEAK"
        elif "SEGV" in msg:
            # địa chỉ gần 0 -> giải tham chiếu NULL
            addr = re.search(r"address 0x([0-9a-f]+)", msg)
            code = "NULL_DEREF" if addr and int(addr.group(1), 16) < 4096 else "ARRAY_OOB"
        else:
            code = next((c for k, c in _ASAN_MAP if k in msg), "UNCLASSIFIED")
        msg = re.sub(r" on (unknown )?address 0x[0-9a-f]+.*", "", msg)
        findings.append(
            Finding(
                bug_pattern=code,
                source="asan",
                line=_first_src_line(after),
                message=msg,
            )
        )
    return findings
