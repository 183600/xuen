/* Machine-Aware Partition (MAP) certificate kernel, v2.1.
 *
 * For each machine class (same A_k and same eligibility column), compile the
 * single-machine postcondition table
 *
 *   f[0] = A_k
 *   f[S] = min_{i in sink(S), k in E_i} max(f[S-i], est_i) + p_i
 *          subject to  completion <= h - q_i .
 *
 * Then decide whether R can be partitioned into blocks, each block assigned to
 * a distinct machine class slot, with f[block] < INF.  Machines in one class
 * are interchangeable, so the partition DP only needs the number of used
 * slots per class (we use a machine-subset bitset in the general case).
 */
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#define INF 1000000000

static int *f[8];
static uint64_t *cover;

int map_solve(int n,int m,int h,const int *p,const int *est,const int *q,
              const uint64_t *succ,const uint64_t *elig,const int *A){
    if(n>22 || m>8) return 1;
    int N=1<<n;
    /* classify machines by (A_k, eligibility column over the residual tasks) */
    int cls[8], ncls=0;
    for(int k=0;k<m;k++){
        int c=-1;
        for(int j=0;j<k;j++){
            if(A[j]!=A[k]) continue;
            int same=1;
            for(int i=0;i<n;i++){
                int bi=(int)((elig[i]>>k)&1), bj=(int)((elig[i]>>j)&1);
                if(bi!=bj){ same=0; break; }
            }
            if(same){ c=cls[j]; break; }
        }
        if(c<0) c=ncls++;
        cls[k]=c;
    }
    for(int c=0;c<ncls;c++){
        if(!f[c]) f[c]=(int*)malloc((size_t)(1<<22)*sizeof(int));
        if(!f[c]) return 1;
        int k=-1;
        for(int t=0;t<m;t++) if(cls[t]==c){ k=t; break; }
        f[c][0]=A[k];
        for(int S=1;S<N;S++){
            int best=INF;
            uint64_t T=(uint64_t)S;
            while(T){
                int i=__builtin_ctzll(T); T&=T-1;
                if(succ[i] & (uint64_t)S) continue;
                if(!((elig[i]>>k)&1)) continue;
                int pm=S^(1<<i);
                if(f[c][pm]>=INF) continue;
                int st=f[c][pm]; if(st<est[i]) st=est[i];
                int en=st+p[i];
                if(en<=h-q[i] && en<best) best=en;
            }
            f[c][S]=best;
        }
    }
    if(!cover) cover=(uint64_t*)malloc((size_t)(1<<22)*sizeof(uint64_t));
    if(!cover) return 1;
    memset(cover,0,(size_t)N*sizeof(uint64_t));
    int single_class = (ncls==1);
    cover[0]=1ULL;
    for(int S=1;S<N;S++){
        int low=S&-S, i0=__builtin_ctzll((uint64_t)low);
        int rest=S^low;
        uint64_t res=0;
        int sub=rest;
        for(;;){
            int block=sub|low;
            uint64_t cu=cover[S^block];
            if(cu){
                if(single_class){
                    /* state = number of used machines (0..m-1) */
                    for(int c=0;c<m;c++){
                        if(!((cu>>c)&1ULL)) continue;
                        if(f[0][block]<INF) res |= 1ULL<<(c+1);
                    }
                } else {
                    /* state = subset U of used machine slots */
                    for(int U=0;U<(1<<m);U++){
                        if(!((cu>>U)&1ULL)) continue;
                        for(int k=0;k<m;k++){
                            if((U>>k)&1) continue;
                            if(f[cls[k]][block]<INF)
                                res |= 1ULL<<(U|(1<<k));
                        }
                    }
                }
            }
            if(sub==0) break;
            sub=(sub-1)&rest;
        }
        cover[S]=res;
    }
    if(single_class){
        /* any used count 1..m is fine; full nonempty implies nonzero */
        return cover[N-1]!=0;
    }
    return cover[N-1]!=0;
}
