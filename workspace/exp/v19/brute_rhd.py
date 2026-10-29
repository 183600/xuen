"""Independent brute-force check of RHD with *explicit releases*.

No PACE code is used in the search: state = (rem, machine availability),
earliest start = max(release, max predecessor completion, machine free time).
"""
import random, itertools, json, time

def solve(n,m,p,E,pred,rel,h,use_rhd,use_norm=True):
    succ=[[] for _ in range(n)]
    for j in range(n):
        for i in pred[j]: succ[i].append(j)
    # static tails (longest path to a sink, excluding own p)
    topo=list(range(n))
    q=[0]*n
    for i in reversed(topo):
        q[i]=max([q[j]+p[j] for j in succ[i]] or [0])
    def rec(rem,A,est):
        if rem==0: return True
        if use_norm:
            est=list(est)
            for i in range(n):
                if rem>>i&1:
                    mn=min(A[k] for k in E[i])
                    if est[i]<mn: est[i]=mn
            est=tuple(est)
        if sum(A)+sum(p[i] for i in range(n) if rem>>i&1) > m*h: return False
        ready=[i for i in range(n) if rem>>i&1 and all(not (rem>>j&1) for j in pred[i])]
        if use_rhd:
            v=min(est[i]+p[i] for i in ready)
            ready=[i for i in ready if est[i]<v]
        for i in ready:
            for k in E[i]:
                t=max(A[k],est[i])
                if t+p[i]+q[i]>h: continue
                nA=list(A); nA[k]=t+p[i]
                nest=list(est)
                for j in succ[i]:
                    if rem>>j&1: nest[j]=max(nest[j],t+p[i])
                if rec(rem&~(1<<i),tuple(nA),tuple(nest)): return True
        return False
    return rec((1<<n)-1,tuple([0]*m),tuple(rel))

def gen(rng,n,m):
    p=[rng.randint(1,4) for _ in range(n)]
    pred=[[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random()<rng.choice([0.2,0.35,0.5]): pred[j].append(i)
    E=[sorted(rng.sample(range(m),rng.randint(1,m))) for _ in range(n)]
    rel=[rng.choice([0,0,0,1,2,3,5]) for _ in range(n)]
    return p,E,pred,rel

def main(N=4000,seed=7,nmax=6,use_norm=True):
    rng=random.Random(seed); bad=0; yes=0; nrun=0; t0=time.time()
    for tr in range(N):
        n=rng.randint(3,nmax); m=rng.choice([2,3])
        p,E,pred,rel=gen(rng,n,m)
        tot=sum(p); h=rng.randint(max(max(rel)+max(p), (tot+m-1)//m), tot+max(rel))
        a=solve(n,m,p,E,pred,rel,h,False,use_norm)
        b=solve(n,m,p,E,pred,rel,h,True,use_norm)
        nrun+=1; yes+=1 if a else 0
        if a!=b:
            bad+=1
            print('MISMATCH n',n,'m',m,'p',p,'E',E,'pred',pred,'rel',rel,'h',h,'full',a,'rhd',b)
            if bad>=3: break
    out=dict(N=nrun,seed=seed,nmax=nmax,yes=yes,bad=bad,use_norm=use_norm,
             sec=round(time.time()-t0,1))
    print(out)
    fn='exp/v19/res_brute_rhd.json' if use_norm else 'exp/v19/res_brute_rhd_nonorm.json'
    json.dump(out,open(fn,'w'),indent=1)

if __name__=='__main__':
    import sys
    main(int(sys.argv[1]) if len(sys.argv)>1 else 4000,
         int(sys.argv[2]) if len(sys.argv)>2 else 7,
         int(sys.argv[3]) if len(sys.argv)>3 else 6,
         use_norm=('--no-norm' not in sys.argv))
