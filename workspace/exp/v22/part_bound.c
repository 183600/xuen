/* Exact single-machine partition bound (Pi-bound) for PACE.
 *
 * Input (stdin):
 *   n m h
 *   p[0..n-1]
 *   est[0..n-1]      earliest start (release)
 *   q[0..n-1]        longest tail (deadline = h - q[i])
 *   succmask[0..n-1] direct successors as a bit mask
 * Optional argv[1]: witness mask W (subset of the n tasks, in local bits).
 *
 * Output:
 *   beta
 *   mask_1 ... mask_beta        (a minimum partition; global local-bit masks)
 *
 * f[S] = minimum completion time of a single machine processing exactly S,
 *        respecting release est, deadline h-q and precedence inside S.
 * g[S] = minimum number of single-machine-feasible parts covering S.
 * beta = g[full].  If beta > m the state is infeasible (sound relaxation).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define INF 1000000000

static int n, m, h;
static int p[32], est[32], q[32];
static unsigned int succ[32];
static int *f;
static unsigned char *feas;
static unsigned char *g;
static unsigned int *choice;
static int N;

static int popc(unsigned int x){ return __builtin_popcount(x); }

/* global index list for a mask */
static int build_list(unsigned int mask, int *idx){
    int k=0;
    for(int i=0;i<n;i++) if((mask>>i)&1) idx[k++]=i;
    return k;
}

int main(int argc, char **argv){
    if(scanf("%d %d %d",&n,&m,&h)!=3) return 2;
    for(int i=0;i<n;i++) if(scanf("%d",&p[i])!=1) return 2;
    for(int i=0;i<n;i++) if(scanf("%d",&est[i])!=1) return 2;
    for(int i=0;i<n;i++) if(scanf("%d",&q[i])!=1) return 2;
    for(int i=0;i<n;i++) if(scanf("%u",&succ[i])!=1) return 2;
    N = 1<<n;
    f = (int*)malloc(sizeof(int)*N);
    feas = (unsigned char*)malloc(N);
    g = (unsigned char*)malloc(N);
    choice = (unsigned int*)malloc(sizeof(unsigned int)*N);
    if(!f || !feas || !g || !choice) return 3;

    f[0]=0;
    for(int S=1; S<N; S++){
        int best=INF;
        int T=S;
        while(T){
            int lb = T & -T;
            int i = __builtin_ctz(lb);
            T ^= lb;
            if(succ[i] & S) continue;           /* i has a successor in S */
            int pm = S ^ lb;
            if(f[pm] >= INF) continue;
            int st = f[pm] > est[i] ? f[pm] : est[i];
            int en = st + p[i];
            if(en > h - q[i]) continue;
            if(en < best) best = en;
        }
        f[S] = best;
    }
    for(int S=1; S<N; S++) feas[S] = (f[S] < INF);

    unsigned int W = (argc > 1) ? (unsigned int)strtoul(argv[1],0,0) : (unsigned int)(N-1);
    if(W == 0) W = (unsigned int)(N-1);
    int idx[32]; int k = build_list(W, idx);
    int M = 1<<k;
    /* local feasibility: local mask L -> global mask S */
    unsigned char *lf = (unsigned char*)malloc(M);
    unsigned char *lg = (unsigned char*)malloc(M);
    unsigned int *lch = (unsigned int*)malloc(sizeof(unsigned int)*M);
    if(!lf || !lg || !lch) return 3;
    for(int L=0; L<M; L++){
        unsigned int S=0;
        for(int j=0;j<k;j++) if((L>>j)&1) S |= (1u<<idx[j]);
        lf[L] = feas[S];
    }
    lg[0]=0; lch[0]=0;
    for(int L=1; L<M; L++){
        int low = L & -L;
        int T=L, best=255, arg=0;
        while(T){
            if((T&low) && lf[T]){
                int rest = L ^ T;
                if(lg[rest] + 1 < best){
                    best = lg[rest] + 1;
                    arg = T;
                }
            }
            T = (T-1) & L;
        }
        lg[L] = (unsigned char)best;
        lch[L] = (unsigned int)arg;
    }
    int beta = lg[M-1];
    printf("%d\n", beta);
    if(beta < 255){
        int L = M-1;
        int first=1;
        while(L){
            unsigned int T = lch[L];
            unsigned int S=0;
            for(int j=0;j<k;j++) if((T>>j)&1) S |= (1u<<idx[j]);
            printf(first ? "%u" : " %u", S);
            first=0;
            L ^= T;
        }
        printf("\n");
    }
    if(argc > 2 && strcmp(argv[2], "dump") == 0){
        for(int S=0; S<N; S++) printf("%d%c", f[S], S+1==N?'\n':' ');
    }
    free(f); free(feas); free(g); free(choice); free(lf); free(lg); free(lch);
    return 0;
}
