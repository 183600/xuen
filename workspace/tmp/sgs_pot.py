import sys, time
sys.path[:0]=['exp/v28','exp/v13']
import sgs

def window_bound(tasks, p, r, d, cap):
    # returns (ok, witness) ; witness (a,b,kind,S/M,rhs)
    # endpoints
    starts=set(); ends=set()
    for i in tasks:
        starts.add(r[i]); starts.add(d[i]-p[i])
        ends.add(r[i]+p[i]); ends.add(d[i])
    starts=sorted(x for x in starts if x>=0)
    ends=sorted(x for x in ends)
    H=len(cap)
    for a in starts:
        if a>=H: continue
        # prefix cap
        for b in ends:
            if b<=a or b>H: continue
            C=sum(cap[a:b])
            M=0; Mset=[]
            for i in tasks:
                v=p[i]
                t=r[i]+p[i]-a
                if t<v: v=t
                t=b-(d[i]-p[i])
                if t<v: v=t
                L=b-a
                if L<v: v=L
                if v>0:
                    M+=v; Mset.append(i)
            if M>C:
                return False, ('mand',a,b,Mset,M,C)
            F=0; Fset=[]
            for i in tasks:
                if r[i]>=a and d[i]<=b:
                    F+=p[i]; Fset.append(i)
            if F>C:
                return False, ('full',a,b,Fset,F,C)
    return True,None

def solve(inst,h,rem=None,A=None,est=None,q=None,nodecap=200000,use_pot=True,stats=None):
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
    nodes=[0]; seen=set(); sched={}
    potnodes=[0]; pottime=[0.0]
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
    def dfs(mask,cap,rel):
        nodes[0]+=1
        if nodes[0]>nodecap: raise TimeoutError
        if mask==0: return True
        k=(mask,tuple(cap),key_rel(mask,rel))
        if k in seen: return False
        if use_pot:
            ts=[i for i in tasks if (mask>>i)&1]
            t0=time.perf_counter()
            ok,w=window_bound(ts,p,rel,d,cap)
            pottime[0]+=time.perf_counter()-t0; potnodes[0]+=1
            if not ok:
                seen.add(k); return False
        ready=[i for i in tasks if (mask>>i)&1 and not (predm[i]&mask)]
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
            if dfs(mask^(1<<i),ncap,nrel): return True
            del sched[i]
        seen.add(k); return False
    try: ok=dfs(rem,cap0,[r0[i] for i in range(n)])
    except TimeoutError: ok=None
    if stats is not None:
        stats['nodes']=nodes[0]; stats['pot_nodes']=potnodes[0]; stats['pot_time']=pottime[0]
    return ok,dict(sched)
