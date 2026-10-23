import sys,pickle
sys.path[:0]=['exp/v71','exp/v61','exp/v60','exp/v13']
import numpy as np
from qnc import QNC
from cert import verify
from probe_forceloop import farkas_obj, load

def solve_with(q,bounds):
    q.budget=100000
    return q._solve(bounds,60,100)

def run(inst,h,force_job=None,force_times=None,verbose=True):
    q=QNC(inst,h); q.budget=100000
    base=[(0,1)]*q.lp.base.N
    # root
    res,z=solve_with(q,base)
    if res.status==2: return dict(why='root-no',lp=1)
    if res.status!=0 or z is None: return dict(why='root-other',lp=1)
    supp=[c for c in range(q.lp.base.N) if z[c]>1e-7]
    b2=list(base)
    for c in supp: b2[c]=(0,0)
    res2,z2=solve_with(q,b2)
    if res2.status!=2: return dict(why='sup-feas',lp=2)
    F={q.lp.cols[c] for c in supp}
    cert,s=farkas_obj(q.lp,F)
    E=frozenset(key for cc,key in enumerate(q.lp.cols) if key in F and s[cc]<0)
    jobs={i for i,t in E}
    if len(jobs)!=1: return dict(why='multi',lp=2,E=E)
    i=next(iter(jobs)); times=sorted(t for j,t in E)
    if verbose: print('mine job',i,'times',times)
    # check each forced start
    out=[]
    for t in times:
        b=list(base)
        for c,key in enumerate(q.lp.cols):
            if key[0]==i and key[-1]!=t: b[c]=(0,0)
        rr,zz=solve_with(q,b)
        out.append((t,rr.status))
        if verbose: print('  force',i,t,'status',rr.status)
    return dict(why='split',lp=2+len(times),job=i,times=times,out=out,E=E)

for idx in [5,47]:
    inst,opt=load('exp/v20/holdout_cases50.pkl')[idx]; h=opt-1
    print('\n=== idx',idx,'h',h)
    print(run(inst,h))
