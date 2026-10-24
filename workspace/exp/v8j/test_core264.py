import sys, json, time
sys.path[:0]=['exp/v8j','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from search_hard import make_inst
from cascade import collect, root_with_cuts, cert_for
inst=make_inst(18,3,264,edgep=0.15,hetero=0.5)
leaves,yes,st=collect(inst,32,nodecap=5000,depthcap=100)
print('leaves',len(leaves),'stats',st)
def core_jobs(F,budget=[100000]):
    F=set(F)
    jobs=sorted({i for i,t in F})
    changed=True
    while changed:
        changed=False
        for i in jobs:
            if budget[0]<=0: break
            F2=frozenset((a,t) for a,t in F if a!=i)
            budget[0]-=1
            c=cert_for(inst,32,F2)
            if c is not None:
                F=F2; changed=True
    return frozenset(F)
t0=time.time(); new=[]
for k,(F,c) in enumerate(leaves):
    G=core_jobs(F)
    new.append((G,c))
    print(k,'|F|',len(F),'jobs',len({i for i,t in F}),'->',len(G),'jobs',len({i for i,t in G}),'sizes',sorted(len([1 for a,t in G if a==j]) for j in {i for i,t in G}))
print('core t',round(time.time()-t0,2))
leaves2=[(G,None) for G,c in new]
t0=time.time(); r=root_with_cuts(inst,32,leaves2,verbose=True)
print('root_with_cuts',r,'t',round(time.time()-t0,2))
