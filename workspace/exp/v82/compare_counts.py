import sys,pickle
sys.path[:0]=['exp/v82','exp/v71','exp/v61','exp/v60','exp/v13']
from qnc import QNC
def load(f):
 d=pickle.load(open(f,'rb')); return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]
inst,opt=load('exp/v20/holdout_cases50.pkl')[5]; h=opt-1
for label in ['probe','qls2mine']:
 q=QNC(inst,h); q.budget=100000
 base=[(0,1)]*q.lp.base.N
 r,z=q._solve(base,60,100)
 print(label,'root lp',q.lp_solves,'cuts',len(q.lp.cuts),'status',r.status)
 supp=[c for c in range(q.lp.base.N) if z[c]>1e-7]
 b2=list(base)
 for c in supp: b2[c]=(0,0)
 r2,z2=q._solve(b2,60,100)
 print(label,'mine lp',q.lp_solves,'cuts',len(q.lp.cuts),'status',r2.status)
 for t in [21,22]:
  b=list(base)
  for c,key in enumerate(q.lp.cols):
   if key[0]==8 and key[-1]!=t: b[c]=(0,0)
  rr,zz=q._solve(b,60,100)
  print(label,'child',t,'lp',q.lp_solves,'status',rr.status)
