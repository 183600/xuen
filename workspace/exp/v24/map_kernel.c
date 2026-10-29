/* Machine-Aware Partition (MAP) certificate kernel.
 *
 * Input (stdin):
 *   n m h
 *   p[0..n-1]
 *   est[0..n-1]
 *   q[0..n-1]
 *   succ[0..n-1]   (64-bit masks)
 *   elig[0..n-1]   (machine bitmask)
 *   A[0..m-1]
 * Output:
 *   "1" if R can be partitioned into <=m single-machine-feasible blocks,
 *       each assigned a distinct eligible machine (MAP relaxation feasible)
 *   "0" if no such assignment exists (certified NO)
 *   optional second line: block masks (global local indices)
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#define INF 1000000000

static int n, m, h;
static int p[24], est[24], q[24], A[8];
static uint64_t succm[24], eligm[24];
static int *f[8];
static unsigned char *cover;

static inline int ctz64(uint64_t x){ return __builtin_ctzll(x); }

int main(void){
    if(scanf("%d %d %d",&n,&m,&h)!=3) return 1;
    for(int i=0;i<n;i++) scanf("%d",&p[i]);
    for(int i=0;i<n;i++) scanf("%d",&est[i]);
    for(int i=0;i<n;i++) scanf("%d",&q[i]);
    for(int i=0;i<n;i++) scanf("%llu",(unsigned long long*)&succm[i]);
    for(int i=0;i<n;i++) scanf("%llu",(unsigned long long*)&eligm[i]);
    for(int k=0;k<m;k++) scanf("%d",&A[k]);
    if(n>22){ printf("1\n"); return 0; } /* safety: unknown */
    int N=1<<n;
    for(int k=0;k<m;k++){
        f[k]=(int*)malloc((size_t)N*sizeof(int));
        if(!f[k]) return 2;
        f[k][0]=A[k];
        for(int S=1;S<N;S++){
            int best=INF;
            uint64_t T=(uint64_t)S;
            while(T){
                int i=ctz64(T); T&=T-1;
                if(succm[i] & (uint64_t)S) continue;      /* not last */
                if(!((eligm[i]>>k)&1)) continue;          /* not eligible */
                int pm=S^(1<<i);
                if(f[k][pm]>=INF) continue;
                int st=f[k][pm]; if(st<est[i]) st=est[i];
                int en=st+p[i];
                if(en<=h-q[i] && en<best) best=en;
            }
            f[k][S]=best;
        }
    }
    cover=(unsigned char*)calloc((size_t)N,1);
    if(!cover) return 2;
    cover[0]=(unsigned char)(1u<<m);
    for(int S=1;S<N;S++){
        int low=S&-S, i0=ctz64((uint64_t)low);
        int rest=S^low;
        unsigned char res=0;
        int sub=rest;
        for(;;){
            int block=sub|low;
            int rem=S^block;
            unsigned char cu=cover[rem];
            if(cu & (1u<<m)){
                for(int k=0;k<m;k++){
                    if(!((eligm[i0]>>k)&1)) continue;
                    if(!((cu>>k)&1) && f[k][block]<INF){
                        res |= (unsigned char)(cu | (1u<<k));
                    }
                }
            }
            if(sub==0) break;
            sub=(sub-1)&rest;
        }
        cover[S]=res;
    }
    int full=N-1;
    int ok = (cover[full] & ((1u<<m)-1))!=0;
    printf("%d\n", ok);
    if(ok && cover[full]){
        /* reconstruct one cover: greedy re-run using cover */
        int S=full; unsigned char U=cover[full];
        /* choose a machine k in U and a block containing lowbit */
        int parts[8], np=0;
        while(S){
            int low=S&-S, i0=ctz64((uint64_t)low);
            int rest=S^low; int chosen=0;
            int sub=rest;
            for(;;){
                int block=sub|low;
                int rem=S^block;
                unsigned char cu=cover[rem];
                for(int k=0;k<m && !chosen;k++){
                    if(!((U>>k)&1)) continue;
                    if(!((cu>>k)&1) && f[k][block]<INF && (cu & ~(1u<<k))){
                        parts[np++]=block; S=rem; U=cu & ~(1u<<k); chosen=1; break;
                    }
                }
                if(chosen) break;
                if(sub==0) break;
                sub=(sub-1)&rest;
            }
            if(!chosen){ /* should not happen; fall back */ break; }
        }
        for(int j=0;j<np;j++) printf("%d ",parts[j]);
        printf("\n");
    }
    return 0;
}
