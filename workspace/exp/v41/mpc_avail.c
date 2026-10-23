#include <stdint.h>
#include <stdlib.h>
#include <string.h>

static int n_, m_;
static int *p_, *r_, *d_, *sm_, *av_;
static uint8_t *fk_;      /* f[k][S] : m * (1<<n) */
static uint8_t *memo_;
static uint32_t *stamp_;
static uint32_t cur_stamp_;
static int *ord_;
static long long nodes_;

static int can(int rem, int k) {
    if (rem == 0) return 1;
    if (k >= m_) return 0;
    int idx = rem * m_ + k;
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
    uint8_t *f = fk_ + (size_t)k * (1 << n_);
    for (;;) {
        int T = sub | (1 << i);
        if (f[T] != 255) {
            int free_ = rem ^ T;
            int maximal = 1;
            int ff = free_;
            while (ff) {
                int j = __builtin_ctz((unsigned)ff); ff &= ff - 1;
                if (f[T | (1 << j)] != 255) { maximal = 0; break; }
            }
            if (maximal && can(rem ^ T, k + 1)) {
                memo_[idx] = 1;
                return 1;
            }
        }
        if (sub == 0) break;
        sub = (sub - 1) & rest;
    }
    memo_[idx] = 0;
    return 0;
}

/* 1 iff the residual machine-partition relaxation is INFEASIBLE.
   Machine k starts at av_[k]; internal precedence/deadlines respected. */
int mpc_avail_no(int n, int m, int h, int *p, int *r, int *d, int *succ, int *av) {
    if (n < 0 || n > 12 || m < 1 || m > 16 || h < 0 || h > 63) return -1;
    if (n == 0) return 0;
    n_ = n; m_ = m; p_ = p; r_ = r; d_ = d; sm_ = succ; av_ = av;
    int N = 1 << n;
    if (!fk_) fk_ = (uint8_t*)malloc((size_t)16 * (1 << 12));
    if (!memo_) memo_ = (uint8_t*)malloc((size_t)(1 << 12) * 17);
    if (!stamp_) stamp_ = (uint32_t*)calloc((size_t)(1 << 12) * 17, sizeof(uint32_t));
    if (!ord_) ord_ = (int*)malloc(16 * sizeof(int));
    if (!fk_ || !memo_ || !stamp_ || !ord_) return -1;
    for (int i = 0; i < n; i++) ord_[i] = i;
    for (int i = 0; i < n; i++)
        for (int j = i + 1; j < n; j++) {
            int a = ord_[i], b = ord_[j];
            if (p_[b] > p_[a] || (p_[b] == p_[a] && d_[b] < d_[a])) {
                ord_[i] = b; ord_[j] = a;
            }
        }
    for (int k = 0; k < m; k++) {
        uint8_t *f = fk_ + (size_t)k * N;
        f[0] = (uint8_t)av_[k];
        for (int S = 1; S < N; S++) {
            uint8_t best = 255;
            int ss = S;
            while (ss) {
                int i = __builtin_ctz((unsigned)ss);
                ss &= ss - 1;
                if (sm_[i] & S) continue;
                uint8_t prev = f[S ^ (1 << i)];
                if (prev == 255) continue;
                int st = prev > r_[i] ? prev : r_[i];
                int fin = st + p_[i];
                if (fin <= d_[i] && fin < best) best = (uint8_t)fin;
            }
            f[S] = best;
        }
    }
    cur_stamp_++;
    if (cur_stamp_ == 0) { memset(stamp_, 0, (size_t)(1<<12) * 17 * sizeof(uint32_t)); cur_stamp_ = 1; }
    nodes_ = 0;
    int ok = can(N - 1, 0);
    return ok ? 0 : 1;
}
long long mpc_avail_nodes(void) { return nodes_; }
