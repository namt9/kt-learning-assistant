#include <stdio.h>

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 0;
    int a[1000] = {0};
    for (int i = 0; i < n; i++) scanf("%d", &a[i]);
    int best = 0;
    for (int i = 1; i < n; i++) {
        if (a[i] > a[best]) best = i;
    }
    printf("%d %d\n", a[best], best + 1);
    return 0;
}
