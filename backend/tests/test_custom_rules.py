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


def test_div_by_zero_literal_only():
    src = "int f(int a, int b){\n int x = a / 0;\n int y = a % (0);\n double z = a / 0.0;\n x /= 0;\n return a / b + a / 0x10 + (int)(a / 0.5) + b % 10;\n}"
    assert found(src) == {
        ("DIV_BY_ZERO", 2),
        ("DIV_BY_ZERO", 3),
        ("DIV_BY_ZERO", 4),
        ("DIV_BY_ZERO", 5),
    }


def test_const_condition_unsigned_and_self_compare():
    src = """void f(int n, int a[]) {
    for (unsigned i = n - 1; i >= 0; i--) a[i] = 0;
    size_t k = n;
    while (k >= 0) k--;
    if (n == n) a[0] = 1;
    for (int j = n - 1; j >= 0; j--) a[j] = 0;
    if (a[n] == a[0] || n < a[n] || n >= 0) a[1] = 2;
}"""
    assert found(src) == {("CONST_CONDITION", 2), ("CONST_CONDITION", 4), ("CONST_CONDITION", 5)}


def test_loop_without_exit():
    src = """int f(int n) {
    while (1) { n++; }
    for (;;) n--;
    while (1) { if (n > 3) break; n++; }
    for (;;) { if (n == 0) return n; n--; }
    do { n++; } while (1);
    while (true) { exit(0); }
}"""
    assert found(src) == {("INFINITE_LOOP", 2), ("INFINITE_LOOP", 3)}


def test_return_local_address_but_not_static_or_heap():
    src = """char *dao(char *s) {
    char kq[100];
    return kq;
}
int *tro(void) {
    int x = 5;
    return &x;
}
char *ok1(void) {
    static char buf[10];
    return buf;
}
int *ok2(int n) {
    int *p = malloc(n * sizeof(int));
    return p;
}
char *ok3(char *s) {
    return s;
}"""
    assert {x for x in found(src) if x[0] == "DANGLING_PTR"} == {
        ("DANGLING_PTR", 3),
        ("DANGLING_PTR", 7),
    }
