import sys, json, time
sys.path[:0]=['exp/v8j','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from search_hard import make_inst
from cascade import collect, root_with_cuts
inst=make_inst(18,3,264,edgep=0.15,hetero=0.5)
leaves,yes,st=collect(inst,32,nodecap=5000,depthcap=100)
print('leaves',len(leaves),'failed',sum(1 for F,c in leaves if c is None),'yes',yes is not None,'stats',st)
print('sizes',sorted(len(F) for F,c in leaves)[:20], 'max',max(len(F) for F,c in leaves))
for order in ('size',):
    t0=time.time(); r=root_with_cuts(inst,32,leaves,order=order,verbose=True)
    print('root_with_cuts',r,'t',round(time.time()-t0,2))
