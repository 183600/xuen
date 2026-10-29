import sys,pickle
sys.path[:0]=['exp/v71','exp/v61','exp/v60','exp/v13']
import numpy as np, scipy.sparse as sp
from scipy.optimize import linprog
from qnc import QNC

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
A,hi=q.lp.matrix(); n_eq=q.lp.n_eq; N=q.lp.base.N
r=A.shape[0]-n_eq
present=np.array([cc for cc,key in enumerate(q.lp.cols) if (key[0],key[-1]) not in F],dtype=np.int64)
print('present',len(present),'of',N,'r',r,'n_eq',n_eq)
B=sp.hstack([A[:n_eq].T,A[n_eq:].T]).tocsr()[present]
c=np.zeros(n_eq+r); c[:n_eq]=1.0; c[n_eq:]=hi[n_eq:]
A_eq=np.zeros((1,n_eq+r)); A_eq[0,n_eq:]=1.0
reslp=linprog(c,A_ub=-B,b_ub=np.zeros(len(present)),A_eq=A_eq,b_eq=[1.0],bounds=[(None,None)]*n_eq+[(0,None)]*r,method='highs')
print('dual status',reslp.status,reslp.message,'fun',reslp.fun)
if reslp.status==0:
 y=reslp.x
 s=np.asarray(A.T.dot(y)).ravel()
 print('min slack present',s[present].min(),'obj',hi[n:].dot(y[n:])+y[:n].sum())
 print('y',y)
# Try normalize -b^T y = 1 instead of sum y_ub=1
# vars y_eq free, y_ub >=0; constraints A^T y >=0; obj b^T y <= -eps; normalize -b^T y =1
nv=n_eq+r
c2=np.zeros(nv); c2[:n_eq]=1; c2[n_eq:]=hi[n_eq:]
A_eq2=np.zeros((1,nv)); A_eq2[0,:]=c2
reslp2=linprog(np.zeros(nv),A_ub=-B,b_ub=np.zeros(len(present)),A_eq=A_eq2,b_eq=[-1.0],bounds=[(None,None)]*n_eq+[(0,None)]*r,method='highs')
print('dual2 status',reslp2.status,reslp2.message, 'fun',reslp2.fun)
