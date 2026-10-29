import sys,pickle
sys.path[:0]=['exp/v71','exp/v61','exp/v60','exp/v13']
import numpy as np, scipy.sparse as sp
from scipy.optimize import linprog
from qnc import QNC
from cert import DENS, verify, _row_meta

def farkas_obj(lp, forbid, dens=DENS):
    A,hi=lp.matrix(); n_eq=lp.n_eq; N=lp.base.N; n=lp.n
    r=A.shape[0]-n_eq
    present=np.array([cc for cc,key in enumerate(lp.cols) if (key[0],key[-1]) not in forbid],dtype=np.int64)
    if len(present)==0: return None,None
    B=sp.hstack([A[:n_eq].T,A[n_eq:].T]).tocsr()[present]
    # objective vector b^T y = sum y_eq + hi^T y_ub
    b=np.concatenate([np.ones(n_eq), hi[n_eq:]])
    # normalize b^T y = -1
    res=linprog(np.zeros(n_eq+r), A_ub=-B, b_ub=np.zeros(len(present)),
                A_eq=[b], b_eq=[-1.0],
                bounds=[(None,None)]*n_eq+[(0,None)]*r, method='highs')
    if res.status!=0:
        return None,res
    for D in dens:
        y=np.rint(res.x*D).astype(np.int64)
        s=np.asarray(A.T.dot(y)).ravel()
        bt=int(b.dot(y))
        if s[present].min()>=0 and bt<0:
            meta=_row_meta(lp.base)+[('dom',i,j,t) for (i,j,t) in lp.cuts]
            yb=y[n:]
            cert=dict(kind='packing',scale=D,
                beta=[(m[1],m[2],int(yb[k])) for k,m in enumerate(meta) if m[0]=='cap' and yb[k]],
                dom=[(m[1],m[2],m[3],int(yb[k])) for k,m in enumerate(meta) if m[0]=='dom' and yb[k]],
                exp=[(m[1],m[2],int(yb[k])) for k,m in enumerate(meta) if m[0]=='exp' and yb[k]],
                alpha=[int(v) for v in y[:n]], obj=bt, farkas=res.fun,
                cuts=[meta[k] for k in range(len(meta)) if yb[k]])
            return cert,s
    return None,res

def load(f):
 d=pickle.load(open(f,'rb')); return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]
for idx in [5,47]:
 inst,opt=load('exp/v20/holdout_cases50.pkl')[idx]; h=opt-1
 q=QNC(inst,h); q.budget=10000
 bounds=[(0,1)]*q.lp.base.N
 res,z=q._solve(bounds,60,100)
 supp=[c for c in range(q.lp.base.N) if z[c]>1e-7]
 F={q.lp.cols[c] for c in supp}
 for c in supp: bounds[c]=(0,0)
 res2,z2=q._solve(bounds,60,100)
 print('\nidx',idx,'status',res2.status,'support',len(supp))
 cert,s=farkas_obj(q.lp,F)
 print('cert',cert is not None, 'scale',None if cert is None else cert['scale'],'obj',None if cert is None else cert['obj'])
 if cert:
  E=frozenset(key for cc,key in enumerate(q.lp.cols) if key in F and s[cc]<0)
  print('E size',len(E),'jobs',len({i for i,t in E}),'verifyE',verify(inst,h,cert,forbid=E,elig_aware=q.elig))
  print('E',sorted(E)[:40])
