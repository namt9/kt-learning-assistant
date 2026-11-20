#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(void) {
    char s[1001];
    if (scanf("%1000s", s) != 1) return 0;
    int len = strlen(s);
    char *st = malloc(len + 1);
    if (st == NULL) return 1;
    int top = 0, ok = 1;
    for (int i = 0; i < len && ok; i++) {
        char c = s[i];
        if (c == '(' || c == '[') {
            st[top++] = c;
        } else {
            char want = c == ')' ? '(' : '[';
            if (top == 0 || st[top - 1] != want) ok = 0;
            else top--;
        }
    }
    printf("%s\n", ok && top == 0 ? "YES" : "NO");
    free(st);
    return 0;
}
