#include <stdio.h>
int main(void) {
    int n, x, sum = 0;
    scanf("%d", &n);
    for (int i = 0; i < n; i++) {
        scanf("%d", &x);
        sum += x;
    }
    double avg = sum / n;
    printf("%.2f\n", avg);
    return 0;
}
