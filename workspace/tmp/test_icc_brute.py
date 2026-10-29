import random, sys, json, itertools
sys.path[:0]=['exp/v13','exp/v15','exp/v16','exp/v20','exp/v24','exp/v25','exp/v28','tmp']
import po, icc, root_pc
def brute(inst, h):
    n,m,p=inst['n'],inst['m'],inst['p']; pred,succ=inst['pred'],inst['succ']
    indeg=[0]*n
    for i in range(n):
        for j in succ[i]: indeg[j]+=1
    q=[i for i in range(n) if indeg[i]==0]; topo=[]
    while q:
        u=q.pop(); topo.append(u)
        for v in succ[u]:
            indeg[v]-=1
            if indeg[v]==0: q.append(v)
    st=[0]*n
    def rec(k):
        if k==n:
            cnt=[0]*h
            for i in range(n):
                for t in range(st[i],st[i]+p[i]): cnt[t]+=1
            return max(cnt)<=m
        i=topo[k]
        lo=max([st[j]+p[j] for j in pred[i]]+[0])
        for t in range(lo,h-p[i]+1):
            st[i]=t
            if rec(k+1): return True
        return False
    return rec(0)

rng=random.Random(2027)
mis_icc=0; mis_pipe=0; feas=0; ncase=0; icc_hits=0
for trial in range(400):
    n=rng.randint(3,7); m=rng.randint(1,3); h=rng.randint(4,10)
    p=[rng.randint(1,4) for _ in range(n)]
    pred=[[] for _ in range(n)]
    for j in range(1,n):
        for i in range(j):
            if rng.random()<0.22: pred[j].append(i)
    succ=[[] for _ in range(n)]
    for j in range(n):
        for i in pred[j]: succ[i].append(j)
    inst=po.make_inst(p,m,pred)
    est,q=po.heads_tails(inst,0,[0]*n)
    b=brute(inst,h)
    # ICC
    ok,w=icc.icc(inst,inst['full'],tuple([0]*m),est,q,h)
    if not ok:
        icc_hits+=1
        if b: mis_icc+=1; print('ICC FALSE NO',n,m,h,p,pred,w); break
        if not icc.check(inst,inst['full'],tuple([0]*m),est,q,h,w):
            print('ICC CHECK FAIL',w); break
    # pipeline
    v,st=root_pc.pc_solve(inst,h)
    if v is None:
        # undecided is allowed only if no claim; but for n<=7 should decide
        mis_pipe+=1; print('PIPE UNKNOWN',n,m,h,p,pred,st); break
    if bool(v)!=bool(b):
        mis_pipe+=1; print('PIPE MISMATCH',n,m,h,p,pred,'brute',b,'pipe',v,st); break
    ncase+=1; feas+=1 if b else 0
print(json.dumps(dict(n=ncase,feasible=feas,icc_hits=icc_hits,mis_icc=mis_icc,mis_pipe=mis_pipe)))
