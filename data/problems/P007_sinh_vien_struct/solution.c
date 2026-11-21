#include <stdio.h>

struct SinhVien {
    char ten[51];
    double diem;
};

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 0;
    struct SinhVien ds[100] = {0};
    for (int i = 0; i < n; i++) scanf("%50s %lf", ds[i].ten, &ds[i].diem);
    int best = 0;
    for (int i = 1; i < n; i++) {
        if (ds[i].diem > ds[best].diem) best = i;
    }
    printf("%s %.2f\n", ds[best].ten, ds[best].diem);
    return 0;
}
