import sys, pickle, time
sys.path[:0] = ['exp/v71','exp/v61','exp/v60','exp/v13']
import numpy as np
from qnc import QNC, farkas_int, Budget
from cert import verify

def load(f):
    d = pickle.load(open(f,'rb'))
    return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]

CASES = {
 'holdout50': 'exp/v20/holdout_cases50.pkl',
 'synth45': 'exp/v28/synth2_45.pkl',
 'large_a': 'exp/v14/large_a.pkl',
 'large_b': 'exp/v14/large_b.pkl',
 'large_het': 'exp/v14/large_het.pkl',
 'hard3': 'exp/v13/hard3.pkl',
 'deep8': 'exp/v18/deep.pkl',
}
def get(name, idx):
    inst,opt = load(CASES[name])[idx]
    return inst, opt-1

def run(inst,h,maxiter=20,eps=1e-7,verbose=True):
    q = QNC(inst,h)
    q.budget = 10000
    bounds=[(0,1)]*q.lp.base.N
    res,z = q._solve(bounds, 60, 100)
    rows=[]
    t0=time.time()
    if res.status==2:
        return dict(status='root-no', it=0, rows=rows)
    if res.status!=0 or z is None:
        return dict(status='root-other', it=0, rows=rows)
    deleted=set()
    for it in range(maxiter):
        supp=[c for c in range(q.lp.base.N) if z[c] > eps]
        supp_keys={q.lp.cols[c] for c in supp}
        if verbose: print('iter',it,'support',len(supp),'deleted',len(deleted),'frac',sum(1 for c in range(q.lp.base.N) if eps<z[c]<1-eps))
        # delete support
        for c in supp:
            bounds[c]=(0,0)
        deleted |= supp_keys
        res2,z2 = q._solve(bounds, 60, 100)
        if res2.status==2:
            # extract cert
            F=set(deleted)
            cert,s = farkas_int(q.lp,F)
            if cert is None:
                rows.append(('certfail',len(F)))
                return dict(status='certfail', it=it+1, rows=rows)
            E=frozenset(key for cc,key in enumerate(q.lp.cols) if key in F and s[cc]<0)
            ok=verify(inst,h,cert,forbid=E,elig_aware=q.elig)
            rows.append(dict(it=it+1, kind='no', F=len(F), E=len(E), jobs=len({i for i,t in E}), verify=ok))
            return dict(status='no', it=it+1, rows=rows, E=sorted(E), cert=cert, ok=ok, deleted=len(deleted))
        if res2.status!=0 or z2 is None:
            return dict(status='other', it=it+1, rows=rows)
        z=z2
    return dict(status='maxiter', it=maxiter, rows=rows, deleted=len(deleted))

if __name__=='__main__':
    for name,idx in [('holdout50',5),('holdout50',47),('holdout50',21),('holdout50',32),('holdout50',42),('hard3',2),('hard3',5),('large_het',1)]:
        inst,h=get(name,idx)
        print('\n===',name,idx,'n',inst['n'],'h',h)
        r=run(inst,h,maxiter=30)
        print({k:v for k,v in r.items() if k not in ('rows','cert','E')})
        for row in r['rows']: print(' ',row)
        if 'E' in r:
            print(' E',r['E'][:60], '...' if len(r['E'])>60 else '')
