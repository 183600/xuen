import sys, time, math
sys.path[:0]=['exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from icf import corpora
from po import heads_tails
from rdf import check_schedule

INF=10**9

def prep(inst):
    n=inst['n']; m=inst['m']; p=inst['p']; pred=inst['pred']; succ=inst['succ']; elig=inst['elig']
    est=[0]*n
    # topo
    indeg=[len(pred[i]) for i in range(n)]
    q=[i for i in range(n) if indeg[i]==0]
    topo=[]
    while q:
        i=q.pop()
        topo.append(i)
        for j in succ[i]:
            indeg[j]-=1
            if indeg[j]==0: q.append(j)
    for i in topo:
        est[i]=max([0]+[est[j]+p[j] for j in pred[i]])
    tail=[0]*n
    for i in reversed(topo):
        tail[i]=max([0]+[p[j]+tail[j] for j in succ[i]])
    pred_mask=[0]*n
    for i in range(n):
        for j in pred[i]: pred_mask[i]|=1<<j
    return dict(est=est,tail=tail,pred_mask=pred_mask,topo=topo)

def solve(inst, h, node_budget=100000, order='tail'):
    n=inst['n']; m=inst['m']; p=inst['p']; elig=inst['elig']; succ=inst['succ']
    d=prep(inst); est=d['est']; tail=d['tail']; pred_mask=d['pred_mask']
    starts=[-1]*n; mach=[-1]*n
    occ=[0]*m
    sched=0
    pred_ready=[0]*n
    nodes=0
    best=None
    # sort jobs by tail for branching order
    def popcount(x): return bin(x).count('1')
    # precompute subset masks
    masks=[]
    for mask in range(1,1<<m):
        masks.append((mask,popcount(mask)))
    def lb(unsched):
        # critical path from current ready times
        mx=0
        for i in range(n):
            if not (unsched>>i)&1: continue
            hr=pred_ready[i]
            if est[i]>hr: hr=est[i]
            v=hr+p[i]+tail[i]
            if v>mx: mx=v
        # load bounds
        minfree=[0]*m
        for k in range(m):
            # earliest free time = lowest zero bit
            x=occ[k]
            t=0
            while (x>>t)&1: t+=1
            minfree[k]=t
        for mask,cnt in masks:
            load=0
            for i in range(n):
                if not (unsched>>i)&1: continue
                ok=True
                for k in elig[i]:
                    if not (mask>>k)&1: ok=False; break
                if ok: load+=p[i]
            if load:
                mf=min(minfree[k] for k in range(m) if (mask>>k)&1)
                v=mf+(load+cnt-1)//cnt
                if v>mx: mx=v
        return mx
    def feasible_t(i,k,t0):
        # earliest t>=t0 with interval free and t+p<=h
        t=t0
        pm=p[i]
        while t+pm<=h:
            if (occ[k]>>t) & ((1<<pm)-1) == 0:
                return t
            t+=1
        return None
    def rec(unsched, cur_cmax):
        nonlocal nodes,best
        nodes+=1
        if nodes>node_budget:
            return None
        if unsched==0:
            return (list(starts),list(mach),cur_cmax)
        if lb(unsched)>h:
            return None
        # eligible
        el=[]
        for i in range(n):
            if (unsched>>i)&1 and (pred_mask[i] & ~((1<<n)-1 ^ unsched)) == 0:
                # all preds scheduled => pred_mask subset of scheduled = ~unsched
                pass
        sched_mask=((1<<n)-1)^unsched
        for i in range(n):
            if (unsched>>i)&1 and (pred_mask[i] & sched_mask)==pred_mask[i]:
                hr=pred_ready[i]
                if est[i]>hr: hr=est[i]
                # key: tail desc, then earliest possible start
                el.append((-(tail[i]+p[i]), hr, i))
        el.sort()
        for _,hr,i in el:
            for k in elig[i]:
                t=feasible_t(i,k,hr)
                if t is None: continue
                # place
                starts[i]=t; mach[i]=k
                pm=p[i]
                occ[k] |= ((1<<pm)-1)<<t
                oldpred=[pred_ready[j] for j in succ[i]]
                for j in succ[i]:
                    if pred_ready[j] < t+pm: pred_ready[j]=t+pm
                res=rec(unsched & ~(1<<i), max(cur_cmax,t+pm))
                if res is not None:
                    return res
                # undo
                for j,old in zip(succ[i],oldpred): pred_ready[j]=old
                occ[k] &= ~(((1<<pm)-1)<<t)
                starts[i]=-1; mach[i]=-1
        return None
    t0=time.time()
    res=rec((1<<n)-1,0)
    return dict(found=res is not None, nodes=nodes, t=time.time()-t0, schedule=res)

if __name__=='__main__':
    rows=list(corpora())
    print('rows',len(rows))
    # test a few with weak L, h=OPT-1 (prove no) and h=OPT (find)
    for row in rows[:5]:
        c,name,idx,inst,known=row
        for h in (known-1,known):
            r=solve(inst,h,node_budget=200000)
            print(c,name,idx,'known',known,'h',h,'found',r['found'],'nodes',r['nodes'],'t',round(r['t'],3))
