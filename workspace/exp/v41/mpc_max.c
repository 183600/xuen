#include <stdint.h>
#include <stdlib.h>
#include <string.h>

static int n_, m_;
static int *p_, *r_, *d_, *sm_;
static uint8_t *f_;
static uint8_t *memo_;
static uint32_t *stamp_;
static uint32_t cur_stamp_;
static int *ord_;
static long long nodes_;

static int can(int rem, int k) {
    if (rem == 0) return 1;
    if (k == 0) return 0;
    int idx = rem * (m_ + 1) + k;
    if (stamp_[idx] == cur_stamp_) return memo_[idx];
    stamp_[idx] = cur_stamp_;
    nodes_++;
    int i = -1;
    for (int t = 0; t < n_; t++) {
        int j = ord_[t];
        if (rem & (1 << j)) { i = j; break; }
    }
    int rest = rem ^ (1 << i);
    int sub = rest;
    for (;;) {
        int T = sub | (1 << i);
        if (f_[T] != 255) {
            int free_ = rem ^ T;
            int maximal = 1;
            int ff = free_;
            while (ff) {
                int j = __builtin_ctz((unsigned)ff); ff &= ff - 1;
                if (f_[T | (1 << j)] != 255) { maximal = 0; break; }
            }
            if (!maximal) goto next;
        }
        if (f_[T] != 255 && can(rem ^ T, k - 1)) {
            memo_[idx] = 1;
            return 1;
        }
        next:
        if (sub == 0) break;
        sub = (sub - 1) & rest;
    }
    memo_[idx] = 0;
    return 0;
}

/* 1 iff the machine-partition relaxation is INFEASIBLE (sound NO certificate).
   Internal precedence is respected on each machine; cross-machine precedence is
   dropped, so this is a relaxation. n <= 16, h <= 63. */
int mpc_no(int n, int m, int h, int *p, int *r, int *d, int *succ) {
    if (n < 0 || n > 16 || m < 1 || m > 16 || h < 0 || h > 63) return -1;
    if (n == 0) return 0;
    n_ = n; m_ = m; p_ = p; r_ = r; d_ = d; sm_ = succ;
    int N = 1 << n;
    if (!f_) f_ = (uint8_t*)malloc(1 << 16);
    if (!memo_) memo_ = (uint8_t*)malloc((size_t)(1 << 16) * 17);
    if (!stamp_) stamp_ = (uint32_t*)calloc((size_t)(1 << 16) * 17, sizeof(uint32_t));
    if (!ord_) ord_ = (int*)malloc(16 * sizeof(int));
    if (!f_ || !memo_ || !stamp_ || !ord_) return -1;
    for (int i = 0; i < n; i++) ord_[i] = i;
    for (int i = 0; i < n; i++)
        for (int j = i + 1; j < n; j++) {
            int a = ord_[i], b = ord_[j];
            if (p_[b] > p_[a] || (p_[b] == p_[a] && d_[b] < d_[a])) {
                ord_[i] = b; ord_[j] = a;
            }
        }
    f_[0] = 0;
    for (int S = 1; S < N; S++) {
        uint8_t best = 255;
        int ss = S;
        while (ss) {
            int i = __builtin_ctz((unsigned)ss);
            ss &= ss - 1;
            if (sm_[i] & S) continue;
            uint8_t prev = f_[S ^ (1 << i)];
            if (prev == 255) continue;
            int st = prev > r_[i] ? prev : r_[i];
            int fin = st + p_[i];
            if (fin <= d_[i] && fin < best) best = (uint8_t)fin;
        }
        f_[S] = best;
    }
    cur_stamp_++;
    if (cur_stamp_ == 0) { memset(stamp_, 0, (size_t)N * (m + 1) * sizeof(uint32_t)); cur_stamp_ = 1; }
    nodes_ = 0;
    int ok = can(N - 1, m);
    return ok ? 0 : 1;
}

long long mpc_nodes(void) { return nodes_; }
