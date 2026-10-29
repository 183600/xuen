import sys,pickle
sys.path[:0]=['exp/v82','exp/v71','exp/v61','exp/v60','exp/v13']
from qls2 import QLS2
import pickle
def load(f):
 d=pickle.load(open(f,"rb")); return [(x[0],x[1]) if isinstance(x,tuple) else (x["inst"],x["opt"]) for x in d]
inst,opt=load('exp/v20/holdout_cases50.pkl')[5]; h=opt-1
q=QLS2(inst,h); q.budget=10000; q.nodecap=5000
bounds=[(0,1)]*q.lp.base.N
res,z=q._solve(bounds,60,100)
print('root status',res.status)
got=q._mine(bounds,z)
if got is None: print('mine none')
else:
 E,cert=got; print('E',sorted(E),'jobs',{i for i,t in E})
 print('satisfied',q._satisfied(bounds,E))
 print('live per job', {i:len([1 for c,key in enumerate(q.lp.cols) if key[0]==i and bounds[c]!=(0,0)]) for i in {i for i,t in E}})
