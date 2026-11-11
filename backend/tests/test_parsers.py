"""Kiểm tra bộ phân tích đầu ra công cụ bằng output mẫu (không cần cài cppcheck)."""

from backend.app.rules.tools import parse_cppcheck, parse_gcc, parse_sanitizer


def codes(findings):
    return {(f.bug_pattern, f.line) for f in findings}


def test_parse_gcc_warnings_and_errors():
    out = """main.c: In function 'main':
main.c:5:13: warning: format '%d' expects argument of type 'int *', but argument 2 has type 'int' [-Wformat=]
main.c:9:13: warning: suggest parentheses around assignment used as truth value [-Wparentheses]
main.c:8:13: warning: 'sum' may be used uninitialized [-Wmaybe-uninitialized]
main.c:4:5: error: expected ',' or ';' before 'scanf'
main.c:5:20: error: 'total' undeclared (first use in this function)
main.c:6:5: warning: ignoring return value of 'scanf' [-Wunused-result]
"""
    assert codes(parse_gcc(out)) == {
        ("SCANF_MISSING_AMP", 5),
        ("ASSIGN_IN_COND", 9),
        ("UNINIT_VAR", 8),
        ("SYNTAX_ERROR", 4),
        ("UNDECLARED_ID", 5),
    }


def test_parse_cppcheck():
    out = """7|error|arrayIndexOutOfBounds|Array 'a[10]' accessed at index 10, which is out of bounds.
12|error|memleak|Memory leak: p
5|warning|invalidScanfArgTypeInt|%d in format string (no. 1) requires 'int *' but the argument type is 'int'.
0|information|missingIncludeSystem|Include file: <stdio.h> not found.
9|style|unusedVariable|Unused variable: tmp
8|error|legacyUninitvar|Uninitialized variable: sum
14|warning|ctunullpointer|Null pointer dereference: p
15|style|someNewCheck|Unknown check id
"""
    assert codes(parse_cppcheck(out)) == {
        ("ARRAY_OOB", 7),
        ("MEM_LEAK", 12),
        ("SCANF_MISSING_AMP", 5),
        ("UNUSED_VAR", 9),
        ("UNINIT_VAR", 8),
        ("NULL_DEREF", 14),
        ("UNCLASSIFIED", 15),
    }


def test_parse_asan_and_ubsan():
    out = """main.c:8:13: runtime error: signed integer overflow: 2147483647 + 1 cannot be represented in type 'int'
=================================================================
==1234==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x602000000018 at pc 0x55 bp 0x7f
WRITE of size 4 at 0x602000000018 thread T0
    #0 0x5555 in main /work/main.c:7
    #1 0x7fff in __libc_start_main
==1234==ERROR: LeakSanitizer: detected memory leaks
Direct leak of 20 byte(s) in 1 object(s) allocated from:
    #0 0x7f in malloc
    #1 0x55 in main /tmp/x/main.c:6
==99==ERROR: AddressSanitizer: SEGV on unknown address 0x000000000000 (pc 0x1 bp 0x2 sp 0x3 T0)
    #0 0x1 in main main.c:11
"""
    assert codes(parse_sanitizer(out)) == {
        ("INT_OVERFLOW", 8),
        ("ARRAY_OOB", 7),
        ("MEM_LEAK", 6),
        ("NULL_DEREF", 11),
    }
