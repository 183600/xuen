import sys, time, random, json
sys.path[:0]=['exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from sdecc import SDLP
from po import heads_tails
from chip import chip_bounds
from sage import SAGE, run

def make_inst(n=24,m=3,seed=0,pmin=2,pmax=9,edgep=0.12):
    rng=random.Random(seed)
    p=[rng.randint(pmin,pmax) for _ in range(n)]
    pred=[[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random()<edgep and len(pred[j])<4:
                pred[j].append(i)
        if j>0 and not pred[j] and rng.random()<0.5:
            pred[j].append(rng.randrange(j))
    succ=[[] for _ in range(n)]
    for j in range(n):
        for i in pred[j]: succ[i].append(j)
    elig=[list(range(m)) for _ in range(n)]
    inst={'n':n,'m':m,'p':p,'pred':pred,'succ':succ,'elig':elig}
    inst['pmask']=[sum(1<<j for j in pred[i]) for i in range(n)]
    inst['desc']=[0]*n
    for i in range(n-1,-1,-1):
        d=0
        for j in succ[i]: d|=(1<<j)|inst['desc'][j]
        inst['desc'][i]=d
    inst['full']=(1<<n)-1
    return inst

def milp_feas(inst,h,tl=20):
    n=inst['n']; m=inst['m']
    est,q=heads_tails(inst,0,[0]*n)
    lp=SDLP(inst,h,est,q,use_dom=True,elig_aware=False)
    if lp.N==0: return False
    A=lp.A.tocsr(); neq=lp.n_eq
    cons=[LinearConstraint(A[:neq], np.ones(n), np.ones(n)),
          LinearConstraint(A[neq:], -np.inf*np.ones(A.shape[0]-neq), lp.hi[neq:])]
    r=milp(c=np.zeros(lp.N), integrality=np.ones(lp.N),
           bounds=Bounds(np.zeros(lp.N), np.ones(lp.N)), constraints=cons,
           options={'time_limit':tl})
    if r.status==0: return True
    if r.status==2: return False
    return None

def opt_milp(inst,ub=None,tl=20):
    n=inst['n']
    est,q=heads_tails(inst,0,[0]*n)
    lb=max(est[i]+inst['p'][i]+q[i] for i in range(n))
    if ub is None:
        # simple greedy via chip
        b=chip_bounds(inst)
        ub=b.get('ub') or sum(inst['p'])+max(q)
    while lb<ub:
        mid=(lb+ub)//2
        f=milp_feas(inst,mid,tl)
        if f is True: ub=mid
        elif f is False: lb=mid+1
        else: return None
    return lb

if __name__=='__main__':
    for seed in range(8):
        inst=make_inst(n=24,m=3,seed=seed)
        t0=time.time()
        opt=opt_milp(inst,tl=10)
        print('seed',seed,'opt',opt,'milp_t',round(time.time()-t0,2),flush=True)
        if opt is None: continue
        # run SAGE
        t0=time.time(); r=run(SAGE,inst,opt,'rand24',seed)
        print('  sage opt',r['opt'],'cert',r['certified'],'q',r['queries'],'bb',r['bb_lp'],'certlp',r['cert_lp'],'kind',r['proof_kind'],'t',r['t'],'unknown',r['unknown'],flush=True)
