"""SOP prototype: saturation-driven forcing + residual interval packing."""
import sys,itertools
sys.path.insert(0,'exp/v13')
import po

def ov(s,p,a,b):
    lo=max(s,a); hi=min(s+p,b); return max(0,hi-lo)
def ou(s,p,S): return sum(ov(s,p,a,b) for a,b in S)

def argmin(r,d,p,S):
    lo,hi=r,d-p
    if hi<lo: return []
    vals=[(ou(s,p,S),s) for s in range(lo,hi+1)]
    m=min(v for v,s in vals)
    return [s for v,s in vals if v==m]

def windows(r,d,p,h,forced=None):
    starts=set(r+[d[i]-p[i] for i in range(len(p))]+[0])
    ends=set(d+[r[i]+p[i] for i in range(len(p))]+[h])
    if forced:
        for i,s in forced.items():
            starts.add(s); ends.add(s+p[i])
    starts=sorted(starts); ends=sorted(ends)
    return [(a,b) for a in starts for b in ends if b>a]

def fits(occ,s,p):
    e=s+p
    for x,y in occ:
        if s<y and x<e: return False
    return True

def pack(items,r,d,p,el,obs_by,m,a,b,nodecap=20000):
    order=sorted(items,key=lambda i:(d[i],r[i]))
    nodes=[0]
    def dfs(pos,occ):
        nodes[0]+=1
        if nodes[0]>nodecap: raise TimeoutError
        if pos==len(order): return True
        i=order[pos]
        lo=max(r[i],a); hi=min(d[i]-p[i],b-p[i])
        for k in el[i]:
            cand={lo}
            for (x,y) in occ[k]+obs_by[k]:
                if lo<=y<=hi: cand.add(y)
                if lo<=x-p[i]<=hi: cand.add(x-p[i])
            for s in sorted(cand):
                if fits(occ[k]+obs_by[k],s,p[i]):
                    occ[k].append((s,s+p[i]))
                    if dfs(pos+1,occ): return True
                    occ[k].pop()
        return False
    try:
        return dfs(0,[[] for _ in range(m)]),nodes[0]
    except TimeoutError:
        return None,nodes[0]

def sop(inst,h,forced0=None,verbose=False,nodecap=20000):
    n,m,p=inst['n'],inst['m'],inst['p']; el=inst['elig']
    est,q=po.heads_tails(inst,0,[0]*n)
    r=list(est); d=[h-q[i] for i in range(n)]
    forced=dict(forced0 or {})
    trace=[]
    for it in range(30):
        Ws=windows(r,d,p,h,forced)
        # evaluate every window; collect all tight ones
        rows=[]
        for (a,b) in Ws:
            cap=m*(b-a)
            fov=sum(ov(s,p[i],a,b) for i,s in forced.items())
            rem=[i for i in range(n) if i not in forced]
            W=0
            for i in rem:
                ar=argmin(r[i],d[i],p[i],[(a,b)])
                W+=min(ou(s,p[i],[(a,b)]) for s in ar) if ar else 0
            rows.append((cap-fov-W,a,b,cap,fov,W))
        rows.sort()
        sl,a,b,cap,fov,W=rows[0]
        trace.append(('energy',it,rows[:3],dict(forced)))
        if sl<0:
            return ('NO-ENERGY',trace),forced
        added=[]; bad=False
        for (sl2,a2,b2,cap2,fov2,W2) in rows:
            if sl2!=0: continue
            for i in range(n):
                if i in forced: continue
                ar=argmin(r[i],d[i],p[i],[(a2,b2)])
                if len(ar)==1:
                    if i in forced and forced[i]!=ar[0]: bad=True
                    if i not in forced or forced[i]!=ar[0]:
                        if i in forced and forced[i]!=ar[0]: bad=True
                        else: forced[i]=ar[0]; added.append((i,ar[0],a2,b2))
        trace.append(('tight',it,added))
        if bad: return ('CONFLICT',trace),forced
        if added: continue
        # residual packing on the zero-slack window with most forced overlap
        cand=[x for x in rows if x[0]==0]
        if not cand:
            return ('FIX',trace),forced
        cand.sort(key=lambda x:(-x[4],x[1]))
        sl2,a2,b2,cap2,fov2,W2=cand[0]
        obs=[]
        for i,s in forced.items():
            x,y=max(s,a2),min(s+p[i],b2)
            if x<y: obs.append((i,x,y))
        items=[i for i in range(n) if i not in forced and r[i]>=a2 and d[i]<=b2]
        okany=False; nodes=0; to=False
        for ass in itertools.product(range(m),repeat=len(obs)):
            good=True; ob=[[] for _ in range(m)]
            for (i,x,y),k in zip(obs,ass):
                if k not in el[i]: good=False;break
                if any(x<y2 and x2<y for x2,y2 in ob[k]): good=False;break
                ob[k].append((x,y))
            if not good: continue
            res,nd=pack(items,r,d,p,el,ob,m,a2,b2,nodecap); nodes+=nd
            if res is None: to=True; continue
            if res: okany=True; break
        trace.append(('pack',it,a2,b2,obs,items,okany,nodes,to))
        if not okany and not to:
            return ('NO-PACK',trace),forced
        return ('FIX-PACKOK',trace),forced
    return ('MAXIT',trace),forced
