import sys, time, random, json
sys.path[:0]=['exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from sdecc import SDLP
from po import heads_tails
from chip import chip_bounds
from lbp import lp_threshold
from sage import lp_branch_decide

def make_inst(n,m,seed,edgep=0.10,hetero=0.0):
    rng=random.Random(seed)
    p=[rng.randint(2,9) for _ in range(n)]
    pred=[[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random()<edgep and len(pred[j])<4:
                pred[j].append(i)
    succ=[[] for _ in range(n)]
    for j in range(n):
        for i in pred[j]: succ[i].append(j)
    elig=[]
    for i in range(n):
        if rng.random()<hetero:
            k=rng.randint(1,m)
            elig.append(sorted(rng.sample(range(m),k)))
        else:
            elig.append(list(range(m)))
    inst={'n':n,'m':m,'p':p,'pred':pred,'succ':succ,'elig':elig}
    inst['pmask']=[sum(1<<j for j in pred[i]) for i in range(n)]
    inst['desc']=[0]*n
    for i in range(n-1,-1,-1):
        d=0
        for j in succ[i]: d|=(1<<j)|inst['desc'][j]
        inst['desc'][i]=d
    inst['full']=(1<<n)-1
    return inst

def milp_feas(inst,h,tl=10):
    n=inst['n']; m=inst['m']
    est,q=heads_tails(inst,0,[0]*n)
    elig=any(len(set(inst['elig'][i]))<m for i in range(n))
    lp=SDLP(inst,h,est,q,use_dom=True,elig_aware=elig)
    if lp.N==0: return False
    A=lp.A.tocsr(); neq=lp.n_eq
    cons=[LinearConstraint(A[:neq], np.ones(n), np.ones(n)),
          LinearConstraint(A[neq:], -np.inf*np.ones(A.shape[0]-neq), lp.hi[neq:])]
    r=milp(c=np.zeros(lp.N), integrality=np.ones(lp.N),
           bounds=Bounds(np.zeros(lp.N), np.ones(lp.N)), constraints=cons,
           options={'time_limit':tl})
    return True if r.status==0 else (False if r.status==2 else None)

def opt_milp(inst,tl=10):
    b=chip_bounds(inst)
    if not b.get('ok'): return None,None
    lb,ub=b['lb'],b['ub']
    while lb<ub:
        mid=(lb+ub)//2
        f=milp_feas(inst,mid,tl)
        if f is True: ub=mid
        elif f is False: lb=mid+1
        else: return None,None
    return lb,ub

if __name__=='__main__':
    found=[]
    t0=time.time()
    for seed in range(120):
        inst=make_inst(18,3,seed,edgep=0.12,hetero=0.25)
        b=chip_bounds(inst)
        if not b.get('ok'): continue
        pin=lp_threshold(inst,b['lb'],b['ub'],T=b['ub'])
        if not pin.get('ok'): continue
        L=pin['lb']
        opt,ub=opt_milp(inst,tl=6)
        if opt is None: continue
        if opt-L!=1: continue
        r=lp_branch_decide(inst,L,nodecap=2000,depthcap=60)
        if r['verdict'] is False:
            found.append((seed,opt,L,r['nodes'],r['leaves'],r['depth'],r['lp_solves'],r['t']))
            print('HARD seed',seed,'opt',opt,'L',L,'nodes',r['nodes'],'leaves',r['leaves'],'depth',r['depth'],'t',r['t'],flush=True)
        else:
            print('seed',seed,'opt',opt,'L',L,'verdict',r['verdict'],'nodes',r['nodes'],flush=True)
        if len(found)>=8: break
    print('found',found,'total_t',round(time.time()-t0,2))
    json.dump(found,open('exp/v8j/hard_found.json','w'))
