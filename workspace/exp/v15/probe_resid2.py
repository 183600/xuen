import sys,pickle,itertools
sys.path.insert(0,'exp/v13')
import po

def fits(occ,s,p):
    e=s+p
    for x,y in occ:
        if s<y and x<e: return False
    return True

def place(items, r, d, el, obs_by_m, m, a, b, nodecap=200000):
    # items list of task ids, place each at integer start in [max(r,a), min(d-p,b-p)]
    order=sorted(items,key=lambda i:(d[i]-r[i], - (d[i])))
    nodes=[0]
    def dfs(pos, occ):
        nodes[0]+=1
        if nodes[0]>nodecap: raise TimeoutError
        if pos==len(order): return True
        i=order[pos]
        lo=max(r[i],a); hi=min(d[i]-p[i], b-p[i])
        for k in el[i]:
            for s in range(lo,hi+1):
                if fits(occ[k]+obs_by_m[k],s,p[i]):
                    occ[k].append((s,s+p[i]))
                    if dfs(pos+1,occ): return True
                    occ[k].pop()
        return False
    return dfs(0,[[] for _ in range(m)]),nodes[0]

d=pickle.load(open('exp/v13/hard3.pkl','rb')); rec=d[2]; inst,opt=rec[0],rec[1]
n,m,p=inst['n'],inst['m'],inst['p']; h=opt-1
est,q=po.heads_tails(inst,0,[0]*n); r=list(est); dd=[h-q[i] for i in range(n)]
chain=[0,1,5,7,10,11]; starts={}; t=0
for i in chain: starts[i]=t; t+=p[i]
a,b=11,28
forced={3:8}
obs=[]
for i in chain:
    s=starts[i]
    if s+p[i]>a and s<b: obs.append((i,max(s,a),min(s+p[i],b)))
for i,s in forced.items():
    if s+p[i]>a and s<b: obs.append((i,max(s,a),min(s+p[i],b)))
items=[i for i in range(n) if i not in starts and i not in forced and r[i]>=a and dd[i]<=b]
print('items',items,'obs',obs)
el=inst['elig']
feas=0; nodes=0
for ass in itertools.product(range(m),repeat=len(obs)):
    ok=True; obs_by=[[] for _ in range(m)]
    for (i,x,y),k in zip(obs,ass):
        if k not in el[i]: ok=False;break
        for (x2,y2) in obs_by[k]:
            if x<y2 and x2<y: ok=False;break
        if not ok: break
        obs_by[k].append((x,y))
    if not ok: continue
    ok,nd=place(items,r,dd,el,obs_by,m,a,b); nodes+=nd
    if ok:
        feas+=1; print('FEASIBLE',ass,obs_by)
print('feasible placements',feas,'nodes',nodes)
