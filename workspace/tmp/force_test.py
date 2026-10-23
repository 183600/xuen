import sys, pickle
sys.path[:0] = ['exp/v61','exp/v60','exp/v13']
from lazy import LazySD
from scope import load

def root_force(inst,h,E,job,rounds=60,topk=100,verbose=False):
    ea=any(len(set(inst['elig'][i]))<inst['m'] for i in range(inst['n']))
    lp=LazySD(inst,h,elig_aware=ea)
    bounds=[(0,1)]*lp.base.N
    idx={}
    for cc,key in enumerate(lp.cols): idx[(key[0],key[-1])]=cc
    D=[key for key in idx if key[0]==job]
    comp=[c for c in D if c not in E]
    for c in comp: bounds[idx[c]]=(0,0)
    for r in range(rounds):
        res=lp.solve(bounds)
        if res.status==2: return 'NO',r+1,len(comp)
        if res.status!=0: return 'other',r+1,len(comp)
        viol=lp.separate(res.x,topk=topk)
        if not viol: return 'FEAS',r+1,len(comp)
        for _,i,j,t in viol:
            if (i,j,t) not in lp.cutset:
                lp.cutset.add((i,j,t)); lp.cuts.append((i,j,t))
    return 'ROUNDCAP',rounds,len(comp)

for f,idx,job,E in [('exp/v20/holdout_cases50.pkl',5,7,[(7,21),(7,22),(7,23)]),
                    ('exp/v20/holdout_cases50.pkl',47,11,[(11,32)])]:
    inst,opt=load(f)[idx]; h=opt-1
    print('idx',idx,'h',h,'force',job,E,'->',root_force(inst,h,set(E),job))
