import sys,random
sys.path.insert(0,'exp/v16')
from pack_chrono import place_chrono
from order_sop import place as place_left

def place_full(items,r,d,p,el,obs_by,m,a,b,nodecap=300000):
    order=sorted(items,key=lambda i:(d[i],r[i]))
    nodes=[0]
    def dfs(pos,occ):
        nodes[0]+=1
        if nodes[0]>nodecap: raise TimeoutError
        if pos==len(order): return True
        i=order[pos]; lo=max(r[i],a); hi=min(d[i]-p[i],b-p[i])
        for k in el[i]:
            for s in range(lo,hi+1):
                blocks=occ[k]+obs_by[k]
                if all(not(s<y and x<s+p[i]) for x,y in blocks):
                    occ[k].append((s,s+p[i]))
                    if dfs(pos+1,occ): return True
                    occ[k].pop()
        return False
    try: return dfs(0,[[] for _ in range(m)]),nodes[0]
    except TimeoutError: return None,nodes[0]

rng=random.Random(1)
bad=0; cases=0; t0=0
for it in range(20000):
    m=rng.choice([2,3]); a=0; b=rng.randint(8,18); L=b-a
    no=rng.randint(0,4)
    obs_by=[[] for _ in range(m)]
    ok=True
    for _ in range(no):
        k=rng.randrange(m); ln=rng.randint(1,4)
        x=rng.randint(a,b-ln); y=x+ln
        if any(x<y2 and x2<y for x2,y2 in obs_by[k]): ok=False;break
        obs_by[k].append((x,y))
    if not ok: continue
    ni=rng.randint(1,6)
    items=list(range(ni))
    p=[rng.randint(1,6) for _ in range(ni)]
    r=[rng.randint(a,b-1) for _ in range(ni)]
    d=[min(b,r[i]+p[i]+rng.randint(0,8)) for i in range(ni)]
    el=[[k for k in range(m) if rng.random()<0.8] or [rng.randrange(m)] for _ in range(ni)]
    # skip infeasible windows
    if any(d[i]-p[i]<r[i] for i in range(ni)): continue
    full,_=place_full(items,r,d,p,el,obs_by,m,a,b)
    left,_=place_left(items,r,d,p,el,obs_by,m,a,b)
    chrono,_=place_chrono(items,r,d,p,el,obs_by,m,a,b)
    cases+=1
    if full!=left or full!=chrono:
        bad+=1
        print('MISMATCH full',full,'left',left,'chrono',chrono,'m',m,'L',L,'p',p,'r',r,'d',d,'el',el,'obs',obs_by)
        if bad>=5: break
print('cases',cases,'mismatch',bad)
