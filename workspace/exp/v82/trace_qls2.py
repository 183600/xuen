import sys,pickle
sys.path[:0]=['exp/v82','exp/v71','exp/v61','exp/v60','exp/v13']
from qls2 import QLS2
import pickle
def load(f):
 d=pickle.load(open(f,'rb')); return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]
inst,opt=load('exp/v20/holdout_cases50.pkl')[5]; h=opt-1
q=QLS2(inst,h); q.budget=10000; q.nodecap=5000
# monkey patch search to trace
orig=q._search
def search(bounds,depth):
 F=q._forbids(bounds)
 print('  '*depth,'ENTER depth',depth,'nodes',q.nodes,'F',len(F),'lp',q.lp_solves)
 v,why=orig(bounds,depth)
 print('  '*depth,'EXIT',v,why,'lp',q.lp_solves)
 return v,why
q._search=search
v,st=q.decide()
print('VERDICT',v,st)
print('splits',q.splits,'mines',q.mines,'events',q.split_events)
for p in q.proofs:
 print(p[0],'F',len(p[1]),'E',len(p[2]),p[4],sorted(p[2])[:8])
