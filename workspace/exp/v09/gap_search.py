import sys, random, math, json, time
sys.path.insert(0,'.'); sys.path.insert(0,'v09')
from lp import frac_pack, frac_lb

def feasible(sizes,m,C):
    sizes=sorted(sizes,reverse=True); bins=[0]*m
    def dfs(i):
        if i==len(sizes): return True
        s=sizes[i]; seen=set()
        for k in range(m):
            if bins[k]+s<=C and bins[k] not in seen:
                seen.add(bins[k]); bins[k]+=s
                if dfs(i+1): return True
                bins[k]-=s
        return False
    return dfs(0)

def bin_opt(sizes,m):
    lo=max(max(sizes), math.ceil(sum(sizes)/m)); b=[0]*m
    for s in sorted(sizes,reverse=True):
        k=min(range(m),key=lambda x:b[x]); b[k]+=s
    hi=max(b)
    for C in range(lo,hi):
        if feasible(sizes,m,C): return C
    return hi

rng=random.Random(11); gaps=[]; t0=time.time()
N=400
for tr in range(N):
    m=rng.choice([3,4]); n=rng.randint(7,11)
    sizes=[rng.randint(2,12) for _ in range(n)]
    OPT=bin_opt(sizes,m)
    L=frac_lb(sizes,m,max(max(sizes),math.ceil(sum(sizes)/m)),OPT)
    if L<OPT:
        gaps.append(dict(m=m,sizes=sizes,OPT=OPT,L=L,n=n))
        print('GAP',m,sizes,'OPT',OPT,'LCFG',L,flush=True)
print('trials',N,'gaps',len(gaps),'time',round(time.time()-t0,1))
json.dump(gaps,open('gaps.json','w'),indent=1)
