#include <stdio.h>
int main(void) {
    int n;
    long long sum = 0;
    scanf("%d", &n);
    for (int i = 0; i < n; i++) {
        int x;
        scanf("%d", &x);
        if (x = 0) continue;
        sum += x;
    }
    printf("%lld\n", sum);
    return 0;
}
