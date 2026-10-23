#include <stdint.h>
#include <stdlib.h>
#include <string.h>

static int n_, m_;
static int *p_, *r_, *d_;
static uint64_t *f_;
static int8_t *memo_;
static int W_;

static int can(int rem, int k) {
    if (rem == 0) return 1;
    if (k == 0) return 0;
    int idx = rem * (m_ + 1) + k;
    if (memo_[idx] >= 0) return memo_[idx];
    int i = __builtin_ctz((unsigned)rem);
    int rest = rem ^ (1 << i);
    int sub = rest;
    for (;;) {
        int T = sub | (1 << i);
        if (f_[T] && can(rem ^ T, k - 1)) {
            memo_[idx] = 1;
            return 1;
        }
        if (sub == 0) break;
        sub = (sub - 1) & rest;
    }
    memo_[idx] = 0;
    return 0;
}

/* Returns 1 iff the assignment relaxation is INFEASIBLE (a sound NO certificate).
   n <= 16, h <= 63. Returns 0 (unknown) on out-of-range inputs. */
int assign_no(int n, int m, int h, int *p, int *r, int *d) {
    if (n < 0 || n > 16 || m < 1 || m > 16 || h < 0 || h > 63) return 0;
    if (n == 0) return 0;
    n_ = n; m_ = m; p_ = p; r_ = r; d_ = d;
    int N = 1 << n;
    f_ = (uint64_t*)calloc((size_t)N, sizeof(uint64_t));
    if (!f_) return 0;
    f_[0] = 1;
    for (int S = 1; S < N; S++) {
        uint64_t x = 0;
        int ss = S;
        while (ss) {
            int i = __builtin_ctz((unsigned)ss);
            ss &= ss - 1;
            uint64_t b = f_[S ^ (1 << i)];
            if (!b) continue;
            int ri = r_[i], pi = p_[i], di = d_[i];
            int fin = ri + pi;
            if (fin > di || fin > 63) continue;
            uint64_t y;
            if (ri == 0) {
                y = b << pi;
            } else {
                uint64_t low = b & ((1ULL << ri) - 1);
                uint64_t high = b >> ri;
                y = high << fin;
                if (low) y |= 1ULL << fin;
            }
            if (di < 63) y &= (1ULL << (di + 1)) - 1;
            x |= y;
        }
        f_[S] = x;
    }
    memo_ = (int8_t*)malloc((size_t)N * (m + 1));
    if (!memo_) { free(f_); return 0; }
    memset(memo_, -1, (size_t)N * (m + 1));
    int full = N - 1;
    int ok = can(full, m);
    free(memo_);
    free(f_);
    return ok ? 0 : 1;
}
