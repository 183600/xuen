import sys, pickle, time, signal
sys.path[:0] = ['exp/v61','exp/v60','exp/v13']
sys.setrecursionlimit(100000)
from alc import ALC
from scope import load
rows=load('exp/v20/holdout_cases50.pkl')
for idx in [0,1,2,3,5,7,11,20,21,47]:
    inst,opt=rows[idx]; t0=time.time()
    a=ALC(inst,opt,cert_on=False)
    try:
        v,st=a.decide(nodecap=3000)
        print(idx,'opt',opt,'v',v,'nodes',st['nodes'],'lp',st['lp_solves'],'t',round(time.time()-t0,2),flush=True)
    except RecursionError:
        print(idx,'RECURSION'); break
    if time.time()-t0>30: print('  slow'); 
