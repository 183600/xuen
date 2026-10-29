import sys, time, random, collections, math
sys.path[:0]=['exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from hap import weak_rows
from po import heads_tails
from rdf import check_schedule

def dfs_repair(inst, h, R, starts0, machs0, node_budget=2000, rng=None, order_mode=0):
    n=inst['n']; m=inst['m']; p=inst['p']; elig=inst['elig']; succ=inst['succ']; pred=inst['pred']
    est,q=heads_tails(inst,0,[0]*n)
    R=set(R)
    starts=list(starts0); machs=list(machs0)
    fixed=[i for i in range(n) if i not in R]
    # fixed feasibility
    for i in fixed:
        if starts[i]+p[i]+q[i]>h: return None,0,'fixed-tail'
    # busy intervals from fixed
    busy=[[] for _ in range(m)]
    for i in fixed:
        busy[machs[i]].append((starts[i],starts[i]+p[i]))
    for k in range(m): busy[k].sort()
    # release/deadline from fixed boundaries
    rel={}; dead={}
    for i in R:
        lo=est[i]; hi=h-p[i]
        for j in pred[i]:
            if j not in R: lo=max(lo,starts[j]+p[j])
        for j in succ[i]:
            if j not in R: hi=min(hi,starts[j]-p[i])
        rel[i]=lo; dead[i]=hi
        if lo>hi: return None,0,'empty-domain'
    # topological order within R
    def topo():
        rem={i:len([j for j in pred[i] if j in R]) for i in R}
        out=[]; ready=[i for i in R if rem[i]==0]
        while ready:
            ready.sort(key=lambda i:(rel[i],-q[i],i))
            i=ready.pop(0); out.append(i)
            for j in succ[i]:
                if j in R:
                    rem[j]-=1
                    if rem[j]==0: ready.append(j)
        return out if len(out)==len(R) else None
    order=topo()
    if order is None: return None,0,'cycle'
    # We search over permutations of a precedence-feasible order; but dynamic eligibility is better.
    nodes=0
    sched=set()
    def earliest(busy_k, base, dur, latest):
        t=base
        for a,b in busy_k:
            if t+dur<=a: break
            if t<b: t=b
        return t if t+dur<=latest else None
    def rec():
        nonlocal nodes
        nodes+=1
        if nodes>node_budget: return False
        if len(sched)==len(R): return True
        # eligible in R
        cand=[]
        for i in R:
            if i in sched: continue
            if any(j in R and j not in sched for j in pred[i]): continue
            base=rel[i]
            for j in pred[i]:
                if j in R: base=max(base,starts[j]+p[j])
            cand.append((-(q[i]+p[i]), base, i))
        if not cand: return False
        cand.sort()
        for _,base,i in cand:
            for k in sorted(elig[i]):
                t=earliest(busy[k],base,p[i],dead[i])
                if t is None: continue
                starts[i]=t; machs[i]=k
                busy[k].append((t,t+p[i])); busy[k].sort()
                sched.add(i)
                if rec(): return True
                sched.remove(i)
                busy[k].remove((t,t+p[i]))
                starts[i],machs[i]=starts0[i],machs0[i]
        return False
    ok=rec()
    return (starts,machs) if ok else None, nodes, ('ok' if ok else 'exhausted' if nodes<=node_budget else 'budget')

def lns_bt(inst, U0, s0, m0, known=None, attempts=60, kmax=12, node_budget=2000, seed=0):
    rng=random.Random(12345+seed)
    n=inst['n']; p=inst['p']
    est,q=heads_tails(inst,0,[0]*n)
    best=U0; bs=list(s0); bm=list(m0)
    tot_nodes=0; status=collections.Counter(); t0=time.time()
    for it in range(attempts):
        if best<=1: break
        h=best-1
        viol=[i for i in range(n) if bs[i]+p[i]+q[i]>h]
        if not viol: break
        R=set(viol)
        if len(R)>kmax:
            viol.sort(key=lambda i:bs[i]+p[i]+q[i],reverse=True)
            R=set(viol[:kmax])
        pool=[i for i in range(n) if i not in R]
        def key(i):
            ov=0
            for j in viol:
                if not (bs[i]+p[i]<=bs[j] or bs[j]+p[j]<=bs[i]):
                    if set(inst['elig'][i]) & set(inst['elig'][j]): ov+=1
            adj=sum(1 for j in viol if j in inst['succ'][i] or i in inst['succ'][j])
            return (ov+2*adj+rng.random(), rng.random())
        pool.sort(key=key,reverse=True)
        k=rng.randint(max(len(R),min(6,n)),min(kmax,n))
        R.update(pool[:max(0,k-len(R))])
        res,nodes,st=dfs_repair(inst,h,R,bs,bm,node_budget=node_budget,rng=rng)
        tot_nodes+=nodes; status[st]+=1
        if res is not None:
            ns,nm=res
            if check_schedule(inst,h,ns,nm):
                best=h; bs, bm = ns, nm
                status['improved']+=1
    return best,bs,bm,dict(nodes=tot_nodes,status=dict(status),t=round(time.time()-t0,3),attempts=it+1)

if __name__=='__main__':
    rows=weak_rows(4)
    print('rows',len(rows))
    out=[]
    for j,(c,name,idx,inst,known,initial) in enumerate(rows[:30]):
        L,U,s,m,proof=initial
        best,bs,bm,st=lns_bt(inst,U,s,m,known=known,attempts=40,kmax=10,node_budget=1500,seed=j)
        print(j,c,name,idx,'known',known,'U0',U,'->',best,'gap',best-known,'t',st['t'],'nodes',st['nodes'],st['status'])
        out.append(best-known)
    print('opt count',sum(x==0 for x in out),'/',len(out),'avg gap',sum(out)/len(out))
