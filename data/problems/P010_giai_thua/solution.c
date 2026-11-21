#include <stdio.h>

long long giai_thua(int n) {
    if (n <= 1) return 1;
    return n * giai_thua(n - 1);
}

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 0;
    printf("%lld\n", giai_thua(n));
    return 0;
}
