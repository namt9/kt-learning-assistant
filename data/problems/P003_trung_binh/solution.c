#include <stdio.h>

int main(void) {
    int n, x, sum = 0;
    if (scanf("%d", &n) != 1) return 0;
    for (int i = 0; i < n; i++) {
        scanf("%d", &x);
        sum += x;
    }
    double avg = (double)sum / n;
    printf("%.2f\n", avg);
    return 0;
}
