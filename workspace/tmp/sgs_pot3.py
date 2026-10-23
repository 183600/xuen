import sys, time
sys.path[:0]=['exp/v28','exp/v13']

def make_windows(tasks,p,r,d,cap):
    H=len(cap)
    starts=sorted(set([r[i] for i in tasks]+[d[i]-p[i] for i in tasks]))
    ends=sorted(set([r[i]+p[i] for i in tasks]+[d[i] for i in tasks]))
    return starts,ends,H

def bound(tasks,p,r,d,cap,mode='both'):
    starts,ends,H=make_windows(tasks,p,r,d,cap)
    # prefix cap
    pc=[0]*(H+1)
    for t in range(H): pc[t+1]=pc[t]+cap[t]
    for a in starts:
        if a<0 or a>=H: continue
        for b in ends:
            if b<=a or b>H: continue
            C=pc[b]-pc[a]
            if mode in ('both','full'):
                F=0
                for i in tasks:
                    if r[i]>=a and d[i]<=b: F+=p[i]
                if F>C: return ('full',a,b,F,C)
            if mode in ('both','mand'):
                M=0; L=b-a
                for i in tasks:
                    v=p[i]
                    t=r[i]+p[i]-a
                    if t<v: v=t
                    t=b-(d[i]-p[i])
                    if t<v: v=t
                    if L<v: v=L
                    if v>0: M+=v
                if M>C: return ('mand',a,b,M,C)
    return None

def solve(inst,h,rem=None,A=None,est=None,q=None,nodecap=200000,mode='both',gate=None,every=1,stats=None):
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
    cap0=[sum(1 for k in range(m) if A[k]<=t) for t in range(h)]
    nodes=[0]; seen=set(); sched={}; calls=[0]; cuts=[0]; cutkind={}; pottime=[0.0]; byfan={}
    def key_rel(mask,rel): return tuple(rel[i] for i in tasks if (mask>>i)&1)
    def earliest(cap,t0,pi,hi):
        t=max(t0,0)
        while t+pi<=hi:
            ok=True
            for u in range(t,t+pi):
                if cap[u]<=0: ok=False; break
            if ok: return t
            t+=1
        return None
    def dfs(mask,cap,rel,depth):
        nodes[0]+=1
        if nodes[0]>nodecap: raise TimeoutError
        if mask==0: return True
        k=(mask,tuple(cap),key_rel(mask,rel))
        if k in seen: return False
        ts=[i for i in tasks if (mask>>i)&1]
        ready=[i for i in ts if not (predm[i]&mask)]
        if depth%every==0:
            E=sum(cap[a] for a in range(h))-sum(p[i] for i in ts)
            if gate is None or E<=gate:
                t0=time.perf_counter()
                w=bound(ts,p,rel,d,cap,mode)
                pottime[0]+=time.perf_counter()-t0; calls[0]+=1
                if w:
                    cuts[0]+=1; cutkind[w[0]]=cutkind.get(w[0],0)+1; byfan[len(ready)]=byfan.get(len(ready),0)+1
                    seen.add(k); return False
        cand=[]
        for i in ready:
            t=earliest(cap,rel[i],p[i],d[i])
            if t is not None: cand.append((i,t))
        if not cand:
            seen.add(k); return False
        cand.sort(key=lambda it:(-p[it[0]],d[it[0]]))
        for i,t in cand:
            ncap=list(cap)
            for u in range(t,t+p[i]): ncap[u]-=1
            nrel=list(rel)
            for j in succm[i]:
                if (mask>>j)&1 and t+p[i]>nrel[j]: nrel[j]=t+p[i]
            sched[i]=t
            if dfs(mask^(1<<i),ncap,nrel,depth+1): return True
            del sched[i]
        seen.add(k); return False
    try: ok=dfs(rem,cap0,[r0[i] for i in range(n)],0)
    except TimeoutError: ok=None
    if stats is not None:
        stats.update(nodes=nodes[0],calls=calls[0],cuts=cuts[0],cutkind=cutkind,pot_time=pottime[0],byfan=byfan)
    return ok,dict(sched)
