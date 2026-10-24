import sys
sys.path[:0]=['exp/v8j','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from search_hard import make_inst
from cascade import collect, _domain
inst=make_inst(18,3,264,edgep=0.15,hetero=0.5)
leaves,yes,st=collect(inst,32,nodecap=5000,depthcap=100)
n=inst['n']
def fulljobs(F):
    out=[]
    for i in range(n):
        lo,hi=_domain(inst,32,i)
        dom={(i,t) for t in range(lo,hi+1)}
        if dom and dom<=F: out.append(i)
    return out
for k,(F,c) in enumerate(sorted(leaves,key=lambda z:len(z[0]))):
    fj=fulljobs(F)
    print(k,'|F|',len(F),'jobs',sorted({i for i,t in F}),'full',fj)
