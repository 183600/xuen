import sys, pickle
sys.path[:0]=['exp/v71','exp/v61','exp/v60','exp/v13']
import numpy as np, scipy.sparse as sp
from scipy.optimize import linprog
from qnc import QNC
from cert import DENS

def farkas_ub(lp, forbid, dens=DENS):
    A,hi=lp.matrix(); n_eq=lp.n_eq; N=lp.base.N
    r=A.shape[0]-n_eq
    present=np.array([cc for cc,key in enumerate(lp.cols) if (key[0],key[-1]) not in forbid],dtype=np.int64)
    if len(present)==0: return None,None
    B=sp.hstack([A[:n_eq].T,A[n_eq:].T]).tocsr()[present]
    # vars: y_eq (free n_eq), y_ub >=0 (r), mu >=0 (len(present))
    nv=n_eq+r+len(present)
    c=np.zeros(nv); c[:n_eq]=1.0; c[n_eq:n_eq+r]=hi[n_eq:]
    c[n_eq+r:]=1.0
    A_ub=np.zeros((len(present),nv))
    A_ub[:,:n_eq]=np.asarray(B[:,:n_eq].todense())
    A_ub[:,n_eq:n_eq+r]=np.asarray(B[:,n_eq:].todense())
    for k in range(len(present)): A_ub[k,n_eq+r+k]=1.0
    A_ub=-A_ub
    b_ub=np.zeros(len(present))
    A_eq=np.zeros((1,nv)); A_eq[0,n_eq:n_eq+r]=1.0; A_eq[0,n_eq+r:]=1.0
    bounds=[(None,None)]*n_eq+[(0,None)]*(r+len(present))
    res=linprog(c,A_ub=A_ub,b_ub=b_ub,A_eq=A_eq,b_eq=[1.0],bounds=bounds,method='highs')
    if res.status!=0 or res.fun>=0: return None,res
    for D in dens:
        y=np.rint(res.x*D).astype(np.int64)
        ye=y[:n_eq]; yb=y[n_eq:n_eq+r]; mu=y[n_eq+r:]
        s=np.asarray(A.T.dot(np.concatenate([ye,np.zeros(n_eq)]))).ravel() if False else None
        # compute column slacks for full A: eq^T ye + ub^T yb
        s=np.asarray(A[:n_eq].T.dot(ye)).ravel()+np.asarray(A[n_eq:].T.dot(yb)).ravel()
        # for present columns, s + mu >= 0; for deleted, no restriction
        if np.all(s[present]+mu>=0):
            obj=int(ye.sum()+hi[n_eq:].dot(yb)+mu.sum())
            if obj<0:
                return dict(ye=ye,yb=yb,mu=mu,obj=obj,scale=D,s=s),res
    return None,res

def load(f):
 d=pickle.load(open(f,'rb')); return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]
inst,opt=load('exp/v20/holdout_cases50.pkl')[5]; h=opt-1
q=QNC(inst,h); q.budget=10000
bounds=[(0,1)]*q.lp.base.N
res,z=q._solve(bounds,60,100)
supp=[c for c in range(q.lp.base.N) if z[c]>1e-7]
F={q.lp.cols[c] for c in supp}
for c in supp: bounds[c]=(0,0)
res2,z2=q._solve(bounds,60,100)
print('status',res2.status)
cert,rr=farkas_ub(q.lp,F)
print('cert',cert is not None, 'fun',None if rr is None else rr.fun, 'nfail',len(F))
if cert:
    print('scale',cert['scale'],'obj',cert['obj'],'mu nonzero',int((cert['mu']!=0).sum()),'mu max',cert['mu'].max())
