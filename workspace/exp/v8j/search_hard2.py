import sys, time, random, json
sys.path[:0]=['exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from sdecc import SDLP
from po import heads_tails
from chip import chip_bounds
from lbp import lp_threshold
from sage import lp_branch_decide
from search_hard import make_inst, milp_feas, opt_milp
from collections import Counter

if __name__=='__main__':
    dist=Counter(); found=[]; t0=time.time()
    for seed in range(300):
        inst=make_inst(18,3,seed,edgep=0.15,hetero=0.5)
        b=chip_bounds(inst)
        if not b.get('ok'): dist['nochip']+=1; continue
        pin=lp_threshold(inst,b['lb'],b['ub'],T=b['ub'])
        if not pin.get('ok'): dist['nopin']+=1; continue
        L=pin['lb']
        opt,ub=opt_milp(inst,tl=5)
        if opt is None: dist['milp_none']+=1; continue
        g=opt-L; dist[g]+=1
        if g!=1: continue
        r=lp_branch_decide(inst,L,nodecap=2000,depthcap=60)
        if r['verdict'] is False:
            found.append(dict(seed=seed,opt=opt,L=L,nodes=r['nodes'],leaves=r['leaves'],depth=r['depth'],lp=r['lp_solves'],t=r['t']))
            print('HARD seed',seed,'opt',opt,'L',L,'nodes',r['nodes'],'leaves',r['leaves'],'depth',r['depth'],'t',r['t'],flush=True)
        else:
            print('g1 seed',seed,'opt',opt,'L',L,'verdict',r['verdict'],'nodes',r['nodes'],flush=True)
        if len(found)>=10: break
    print('dist',dist,'found',len(found),'t',round(time.time()-t0,2))
    json.dump(found,open('exp/v8j/hard_found.json','w'))
