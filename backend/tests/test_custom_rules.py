from backend.app.rules.custom import run_custom_rules, strip_comments_and_strings


def found(src):
    return {(f.bug_pattern, f.line) for f in run_custom_rules(src)}


def test_strip_keeps_positions():
    src = 'int a; // if (a = 1)\nprintf("if (x = 2)");\n/* for(;;); */ int b;'
    clean = strip_comments_and_strings(src)
    assert len(clean) == len(src) and clean.count("\n") == src.count("\n")
    assert "if" not in clean and "for" not in clean


def test_scanf_missing_amp_but_not_for_arrays_or_pointers():
    src = """int main(void) {
    int n; char name[20]; int *p;
    scanf("%d", n);
    scanf("%s", name);
    scanf("%d", p);
    scanf("%d %*d %d", &n, n);
}"""
    assert found(src) == {("SCANF_MISSING_AMP", 3), ("SCANF_MISSING_AMP", 6)}


def test_assign_in_condition_ignores_comparisons():
    src = "int f(int x){\n if (x = 0) return 1;\n if (x == 0 || x <= 2 || x != 3) return 2;\n return 0; }"
    assert found(src) == {("ASSIGN_IN_COND", 2)}


def test_stray_semicolon_but_not_do_while():
    src = "void f(int n){ int i;\nfor (i = 0; i < n; i++);\ndo { n--; } while (n > 0);\n}"
    assert found(src) == {("STRAY_SEMICOLON", 2)}


def test_off_by_one():
    src = "int a[10];\nvoid f(void){\n for (int i = 0; i <= 10; i++) a[i] = 0;\n for (int i = 0; i <= 9; i++) a[i] = 0;\n for (int j = 0; j <= n - 1; j++) a[j] = 1;\n}"
    assert ("OFF_BY_ONE", 3) in found(src)
    assert ("OFF_BY_ONE", 5) not in found(src)


def test_int_division():
    src = "int main(void){\n int s = 7, n = 2;\n double avg = s / n;\n double ok = (double)s / n;\n float f = s / 2.0;\n}"
    assert found(src) == {("INT_DIVISION", 3)}


def test_malloc_without_free():
    assert ("MEM_LEAK", 1) in found("int *p = malloc(4);\nint main(void){ return 0; }")
    assert not found("int *p;\nvoid f(void){ p = malloc(4); free(p); }")
