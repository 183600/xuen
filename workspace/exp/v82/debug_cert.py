import sys, pickle
sys.path[:0]=['exp/v71','exp/v61','exp/v60','exp/v13']
import numpy as np
from qnc import QNC, farkas_int
import cert as v60cert

def load(f):
 d=pickle.load(open(f,'rb')); return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]
inst,opt=load('exp/v20/holdout_cases50.pkl')[5]; h=opt-1
q=QNC(inst,h); q.budget=10000
bounds=[(0,1)]*q.lp.base.N
res,z=q._solve(bounds,60,100)
print('root',res.status, 'n',q.lp.base.N,'n_eq',q.lp.n_eq,'cuts',len(q.lp.cuts))
supp=[c for c in range(q.lp.base.N) if z[c]>1e-7]
F={q.lp.cols[c] for c in supp}
print('support',len(supp))
for c in supp: bounds[c]=(0,0)
res2,z2=q._solve(bounds,60,100)
print('after delete',res2.status, 'message',res2.message)
print('shapes',q.lp.matrix()[0].shape, q.lp.matrix()[1].shape)
cert,s=farkas_int(q.lp,F)
print('farkas_int',cert is not None)
if cert: print('slack min',s.min(), 'obj',cert['obj'])
# try v60 integer_certificate with forbid
c2=v60cert.integer_certificate(inst,h,forbid=F)
print('v60 integer_certificate', c2 is not None)
if c2: print('c2',c2['scale'],c2['obj'],len(c2['beta']),len(c2['dom']))
# try with full support as keys including eligibility
print('elig',q.elig, inst['elig'][0])
