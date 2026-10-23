import sys, pickle
sys.path[:0] = ['exp/v61','exp/v60','exp/v13']
from lazy import LazySD
from scope import load

def root_with_forbid(inst,h,cols,rounds=60,topk=100):
    lp=LazySD(inst,h,elig_aware=any(len(set(inst['elig'][i]))<inst['m'] for i in range(inst['n'])))
    bounds=[(0,1)]*lp.base.N
    idx={}
    for cc,key in enumerate(lp.cols): idx[(key[0],key[-1])]=cc
    for c in cols:
        if c in idx: bounds[idx[c]]=(0,0)
    for r in range(rounds):
        res=lp.solve(bounds)
        if res.status==2: return 'NO',r+1
        if res.status!=0: return 'other',r+1
        viol=lp.separate(res.x,topk=topk)
        if not viol: return 'FEAS',r+1
        for _,i,j,t in viol:
            if (i,j,t) not in lp.cutset:
                lp.cutset.add((i,j,t)); lp.cuts.append((i,j,t))
    return 'ROUNDCAP',rounds

for f,idx,holes in [('exp/v20/holdout_cases50.pkl',5,[(7,21),(7,22),(7,23)]),
                    ('exp/v20/holdout_cases50.pkl',47,[(11,32)])]:
    inst,opt=load(f)[idx]; h=opt-1
    print('idx',idx,'h',h,'hole',holes)
    for name,cols in [('none',[]),('hole',holes),('Ffirst',[(7,19),(7,20),(7,21),(7,22),(7,23)] if idx==5 else [(11,32)])]:
        print('  ',name,root_with_forbid(inst,h,cols))
