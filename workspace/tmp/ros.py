import sys
sys.path[:0]=['exp/v28','exp/v13','exp/v25']
import cps_lib

def residual_os(inst, rem, A, est, q, h, chain, s, nodecap=200000):
    w=cps_lib._windows(inst,rem,A,est,q,h,chain,s)
    if w is None: return False,0
    r,d=w
    p=inst['p']; n=inst['n']; m=inst['m']
    P=set(chain)
    cap=[sum(1 for k in range(m) if A[k]<=t) for t in range(h)]
    for a,i in enumerate(chain):
        for t in range(s[a],min(h,s[a]+p[i])): cap[t]-=1
    if any(c<0 for c in cap): return False,0
    res=[i for i in range(n) if ((rem>>i)&1) and i not in P]
    rmask=0
    for i in res: rmask|=1<<i
    predm={i:sum(1<<j for j in inst['pred'][i] if (rmask>>j)&1) for i in res}
    succm={i:[j for j in inst['succ'][i] if (rmask>>j)&1] for i in res}
    seen=set(); nodes=[0]
    def earliest(cap,t0,pi,hi):
        t=max(t0,0)
        while t+pi<=hi:
            if all(cap[u]>0 for u in range(t,t+pi)): return t
            t+=1
        return None
    def dfs(mask,cap,rel):
        nodes[0]+=1
        if nodes[0]>nodecap: raise TimeoutError
        if mask==0: return True
        key=(mask,tuple(cap),tuple(rel[i] for i in res if (mask>>i)&1))
        if key in seen: return False
        ready=[i for i in res if (mask>>i)&1 and not (predm[i]&mask)]
        cand=[]
        for i in ready:
            t=earliest(cap,rel[i],p[i],d[i])
            if t is not None: cand.append((i,t))
        if not cand: seen.add(key); return False
        cand.sort(key=lambda it:(-p[it[0]],d[it[0]]))
        for i,t in cand:
            ncap=list(cap)
            for u in range(t,t+p[i]): ncap[u]-=1
            nrel=list(rel)
            for j in succm[i]:
                if (mask>>j)&1 and t+p[i]>nrel[j]: nrel[j]=t+p[i]
            if dfs(mask^(1<<i),ncap,nrel): return True
        seen.add(key); return False
    try: ok=dfs(rmask,cap,r)
    except TimeoutError: ok=None
    return ok,nodes[0]
