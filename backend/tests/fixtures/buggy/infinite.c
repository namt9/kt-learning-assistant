#include <stdio.h>
/* Quên tăng i: vòng lặp không bao giờ dừng.
   Vòng lặp có I/O (scanf) nên trình biên dịch không được giả định nó kết thúc
   (C11 6.8.5p6); kết quả TLE ổn định trên mọi phiên bản gcc và mức tối ưu. */
int main(void) {
    int n, x;
    long long sum = 0;
    scanf("%d", &n);
    int i = 0;
    while (i < n) {
        scanf("%d", &x);
        sum += x;
    }
    printf("%lld\n", sum);
    return 0;
}
