#include <stdio.h>
int main(void) {
    int n, i;
    long long sum = 0;
    scanf("%d", &n);
    for (i = 0; i < n; i++);
    {
        int x;
        scanf("%d", &x);
        sum += x;
    }
    printf("%lld\n", sum);
    return 0;
}
