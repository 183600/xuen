import sys, time
sys.path[:0]=['exp/v28','exp/v13']

def solve(inst,h,rem=None,A=None,est=None,q=None,nodecap=200000,stats=None):
    n,m,p=inst['n'],inst['m'],inst['p']
    if rem is None: rem=inst['full']
    if A is None: A=tuple([0]*m)
    if est is None or q is None:
        import po
        est0,q0=po.heads_tails(inst,0,[0]*n)
        est=est if est is not None else est0
        q=q if q is not None else q0
    tasks=[i for i in range(n) if (rem>>i)&1]
    d={i:h-q[i] for i in tasks}
    r0={i:est[i] for i in tasks}
    predm={i:sum(1<<j for j in inst['pred'][i] if (rem>>j)&1) for i in tasks}
    succm={i:[j for j in inst['succ'][i] if (rem>>j)&1] for i in tasks}
    # exact level bitsets
    cnt=[sum(1 for k in range(m) if A[k]<=t) for t in range(h)]
    E=[0]*(m+1)
    for t,c in enumerate(cnt): E[c]|=1<<t
    fullmask=(1<<h)-1
    seen=set(); sched={}; nodes=[0]
    def key_rel(mask,rel): return tuple(rel[i] for i in tasks if (mask>>i)&1)
    def avail(E):
        a=0
        for c in range(1,m+1): a|=E[c]
        return a
    def runmask(a,p):
        r=a
        for i in range(1,p): r &= (a>>i)
        return r
    def earliest(E,a,rel,pi,hi):
        if hi<rel: return None
        r=runmask(a,pi)
        # bits rel..hi
        r &= ((1<<(hi+1))-1) ^ ((1<<rel)-1)
        if not r: return None
        return (r & -r).bit_length()-1
    def place(E,t,pi):
        segmask=((1<<pi)-1)<<t
        NE=list(E)
        moves=[E[c]&segmask for c in range(1,m+1)]
        for c in range(1,m+1):
            NE[c]^=moves[c-1]
            NE[c-1]|=moves[c-1]
        return NE
    def dfs(mask,E,rel):
        nodes[0]+=1
        if nodes[0]>nodecap: raise TimeoutError
        if mask==0: return True
        k=(mask,tuple(E),key_rel(mask,rel))
        if k in seen: return False
        a=avail(E)
        ready=[i for i in tasks if (mask>>i)&1 and not (predm[i]&mask)]
        cand=[]
        for i in ready:
            t=earliest(E,a,rel[i],p[i],d[i]-p[i])
            if t is not None: cand.append((i,t))
        if not cand: seen.add(k); return False
        cand.sort(key=lambda it:(-p[it[0]],d[it[0]]))
        for i,t in cand:
            NE=place(E,t,p[i])
            nrel=list(rel)
            for j in succm[i]:
                if (mask>>j)&1 and t+p[i]>nrel[j]: nrel[j]=t+p[i]
            sched[i]=t
            if dfs(mask^(1<<i),NE,nrel): return True
            del sched[i]
        seen.add(k); return False
    try: ok=dfs(rem,E,[r0[i] for i in range(n)])
    except TimeoutError: ok=None
    if stats is not None: stats['nodes']=nodes[0]
    return ok,dict(sched)
