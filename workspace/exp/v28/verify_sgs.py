"""Brute-force validation of SGS completeness on random small instances."""
import random, sys, itertools, json
sys.path[:0]=['exp/v28']
from proto_full import sgs_full

def brute(inst, h):
    n, m, p = inst['n'], inst['m'], inst['p']
    pred, succ = inst['pred'], inst['succ']
    # topological order
    indeg=[0]*n
    for i in range(n):
        for j in succ[i]: indeg[j]+=1
    q=[i for i in range(n) if indeg[i]==0]; topo=[]
    while q:
        u=q.pop(); topo.append(u)
        for v in succ[u]:
            indeg[v]-=1
            if indeg[v]==0: q.append(v)
    best=None
    # all start vectors with precedence, capacity m
    st=[0]*n
    def rec(k):
        nonlocal best
        if k==n:
            cnt=[0]*h
            for i in range(n):
                for t in range(st[i], st[i]+p[i]): cnt[t]+=1
            if max(cnt)<=m: best=st[:]; return True
            return False
        i=topo[k]
        lo=max([st[j]+p[j] for j in pred[i]]+[0])
        for t in range(lo, h-p[i]+1):
            st[i]=t
            if rec(k+1): return True
        return False
    return rec(0)

rng=random.Random(7)
mis=0; tested=0; feas=0
for trial in range(400):
    n=rng.randint(3,7); m=rng.randint(1,3); h=rng.randint(4,10)
    p=[rng.randint(1,4) for _ in range(n)]
    pred=[[] for _ in range(n)]
    for j in range(1,n):
        # random sparse precedence, i<j with prob
        for i in range(j):
            if rng.random()<0.22: pred[j].append(i)
    succ=[[] for _ in range(n)]
    for j in range(n):
        for i in pred[j]: succ[i].append(j)
    inst=dict(n=n,m=m,p=p,pred=pred,succ=succ,full=(1<<n)-1,
              elig=[list(range(m)) for _ in range(n)])
    # windows: est from heads, d = h - tails (tails=0 if h large -> use h)
    est=[0]*n; indeg=[0]*n
    for i in range(n):
        for j in succ[i]: indeg[j]+=1
    q=[i for i in range(n) if indeg[i]==0]; topo=[]
    while q:
        u=q.pop(); topo.append(u)
        for v in succ[u]:
            indeg[v]-=1
            if indeg[v]==0: q.append(v)
    for i in topo:
        est[i]=max([est[j]+p[j] for j in pred[i]]+[0])
    import po
    est2,qq=po.heads_tails(inst,0,[0]*n)
    b=brute(inst,h)
    s=sgs_full(inst,h,nodecap=10**7,dom=False)
    tested+=1; feas+= 1 if b else 0
    if bool(b)!=bool(s):
        mis+=1
        print('MISMATCH', n,m,h,p,pred,'brute',b,'sgs',s)
        if mis>5: break
print(json.dumps(dict(tested=tested,feasible=feas,mismatch=mis)))
