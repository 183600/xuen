import sys, json, time
sys.path[:0]=['exp/v8j','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from search_hard import make_inst
from cascade import collect, root_with_cuts, cert_for, _elig
from sdecc import SDLP
from po import heads_tails
inst=make_inst(18,3,264,edgep=0.15,hetero=0.5)
leaves,yes,st=collect(inst,32,nodecap=5000,depthcap=100)
print('leaves',len(leaves),'stats',st,flush=True)
cache={}
def status(F):
    F=frozenset(F)
    if F in cache: return cache[F]
    n=inst['n']
    est,q=heads_tails(inst,0,[0]*n)
    lp=SDLP(inst,32,est,q,use_dom=True,elig_aware=_elig(inst),forbid=F)
    if lp.N==0:
        cache[F]=2; return 2
    r=lp.solve()
    cache[F]=r.status
    return r.status
def core_jobs(F,budget):
    F=set(F)
    jobs=sorted({i for i,t in F})
    changed=True
    while changed and budget[0]>0:
        changed=False
        for i in jobs:
            if budget[0]<=0: break
            F2=frozenset((a,t) for a,t in F if a!=i)
            budget[0]-=1
            if status(F2)==2:
                F=F2; changed=True
    return frozenset(F)
for k,(F,c) in enumerate(sorted(leaves,key=lambda z:len(z[0]))[:8]):
    t0=time.time(); G=core_jobs(F,[400])
    print(k,'|F|',len(F),'jobs',len({i for i,t in F}),'->',len(G),'jobs',len({i for i,t in G}),'t',round(time.time()-t0,2),flush=True)
