/* Exact single-machine partition bound with eligibility, bitset C kernel.
 * Local n <= 20.  Returns beta (capped at m+1); if beta <= m, fills parts.
 */
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#define INF 1000000000
typedef unsigned long long u64;

static int n, m, h;
static int p[24], est[24], q[24];
static u64 succ[24], elig[24];
static int *f;
static unsigned char *feas, *g;
static u64 *inter;
static u64 *choice;

int pi_solve(int n_, int m_, int h_,
             const int *p_, const int *est_, const int *q_,
             const u64 *succ_, const u64 *elig_,
             u64 W, int *out_parts, int max_parts, int cap)
{
    n = n_; m = m_; h = h_;
    for (int i = 0; i < n; i++) { p[i]=p_[i]; est[i]=est_[i]; q[i]=q_[i]; succ[i]=succ_[i]; elig[i]=elig_[i]; }
    int idx[24], k=0;
    for (int i=0;i<n;i++) if ((W>>i)&1) idx[k++]=i;
    if (k==0) return 0;
    int N = 1<<k;
    f = (int*)malloc(sizeof(int)*N);
    feas = (unsigned char*)malloc(N);
    g = (unsigned char*)malloc(N);
    inter = (u64*)malloc(sizeof(u64)*N);
    choice = (u64*)malloc(sizeof(u64)*N);
    if(!f||!feas||!g||!inter||!choice) return -1;

    /* local arrays */
    int lp[24], le[24], lq[24]; u64 ls[24], lu[24];
    for (int j=0;j<k;j++) {
        int i=idx[j]; lp[j]=p[i]; le[j]=est[i]; lq[j]=q[i]; ls[j]=0; lu[j]=elig[i];
        for (int t=0;t<k;t++) if ((succ[i]>>idx[t])&1) ls[j] |= (1ULL<<t);
    }
    f[0]=0; inter[0]=~0ULL;
    for (int S=1; S<N; S++) {
        int lb = S & -S; int j = __builtin_ctzll((u64)lb);
        inter[S] = inter[S^lb] & lu[j];
        int best=INF;
        u64 T=S;
        while(T){
            int b = T & -T; int i = __builtin_ctzll((u64)b); T ^= b;
            if (ls[i] & S) continue;          /* i has successor in S */
            int pm = S ^ b;
            if (f[pm] >= INF) continue;
            int st = f[pm] > le[i] ? f[pm] : le[i];
            int en = st + lp[i];
            if (en > h - lq[i]) continue;
            if (en < best) best = en;
        }
        f[S]=best;
        feas[S] = (best < INF) && (inter[S] != 0);
    }
    g[0]=0; choice[0]=0;
    for (int S=1; S<N; S++) {
        int low = S & -S;
        int best = 255; u64 arg=0;
        u64 T=S;
        while(T){
            if ((T&low) && feas[T]) {
                int rest = S ^ T;
                int gr = g[rest];
                int v = (gr > m) ? (m+1) : (gr + 1);   /* saturating add */
                if (v < best) { best = v; arg = T; if (best==1) break; }
            }
            T=(T-1)&S;
        }
        if (best > m+1) best = m+1;   /* beta>m is all we need */
        g[S]=(unsigned char)best; choice[S]=arg;
    }
    int beta = g[N-1];
    if (beta <= m && out_parts && max_parts>0) {
        int S=N-1, cnt=0;
        while(S && cnt<max_parts){
            u64 T=choice[S];
            u64 G=0;
            for(int j=0;j<k;j++) if((T>>j)&1) G |= (1ULL<<idx[j]);
            out_parts[cnt++]= (int)G; /* truncate for n<=24, fine */
            S ^= (int)T;
        }
    }
    free(f); free(feas); free(g); free(inter); free(choice);
    return beta;
}
