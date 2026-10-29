import sys, time, random, json
sys.path[:0]=['exp/v8j','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from search_hard import make_inst, milp_feas, opt_milp
from chip import chip_bounds
from lbp import lp_threshold
import sage
from cert import DENS

BIG = tuple(range(1, 400)) + (420,480,500,600,720,840,1000,1095,1200,1500,1800,2000,2400,3000,3600,4000,5000,6000,7200,10000,12000,20000,50000,100000)

def run_branch(inst,h,dens,nodecap=4000,depthcap=80):
    orig=sage.integer_certificate
    def wrap(inst,h,use_expect=False,use_dom=True,elig_aware=None,forbid=None,dens_arg=None):
        return orig(inst,h,use_expect=use_expect,use_dom=use_dom,elig_aware=elig_aware,forbid=forbid,dens=dens)
    sage.integer_certificate=wrap
    try:
        r=sage.lp_branch_decide(inst,h,nodecap=nodecap,depthcap=depthcap)
    finally:
        sage.integer_certificate=orig
    return r

if __name__=='__main__':
    base=make_inst(18,3,264,edgep=0.15,hetero=0.5)
    rng=random.Random(7)
    rows=[]; t0=time.time(); tried=0
    for k in range(120):
        inst={key:(list(v) if isinstance(v,list) else v) for key,v in base.items()}
        # deep copy nested
        import copy
        inst=copy.deepcopy(base)
        j=rng.randrange(inst['n']); delta=rng.choice([-1,1])
        inst['p'][j]=max(1,inst['p'][j]+delta)
        b=chip_bounds(inst)
        if not b.get('ok'): continue
        pin=lp_threshold(inst,b['lb'],b['ub'],T=b['ub'])
        if not pin.get('ok'): continue
        L=pin['lb']; opt,ub=opt_milp(inst,tl=8)
        tried+=1
        if opt is None or opt-L!=1: continue
        rd=run_branch(inst,L,DENS); rb=run_branch(inst,L,BIG)
        rows.append(dict(k=k,j=j,delta=delta,opt=opt,L=L,dens_v=rd['verdict'],dens_nodes=rd['nodes'],dens_unknown=rd['unknown'],big_v=rb['verdict'],big_nodes=rb['nodes'],big_unknown=rb['unknown'],dens_t=rd['t'],big_t=rb['t']))
        print('g1',k,'j',j,'d',delta,'opt',opt,'L',L,'dens',rd['verdict'],rd['nodes'],rd['unknown'],'big',rb['verdict'],rb['nodes'],rb['unknown'],flush=True)
    print('tried',tried,'g1',len(rows),'dens_fail',sum(1 for r in rows if r['dens_v'] is None),'big_fail',sum(1 for r in rows if r['big_v'] is None),'t',round(time.time()-t0,1))
    json.dump(rows,open('exp/v8j/pert_probe.json','w'),indent=1)
