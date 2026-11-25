#include <stdio.h>
#include <string.h>

int main(void) {
    char s[101];
    if (scanf("%100s", s) != 1) return 0;
    int len = strlen(s);
    for (int i = 0; i < len / 2; i++) {
        char t = s[i];
        s[i] = s[len - 1 - i];
        s[len - 1 - i] = t;
    }
    printf("%s\n", s);
    return 0;
}
