import sys, pickle
sys.path[:0]=['exp/v71','exp/v61','exp/v60','exp/v13']
from qnc import QNC, farkas_int
from scope import load
for f,idx in [('exp/v20/holdout_cases50.pkl',5),('exp/v20/holdout_cases50.pkl',47)]:
    inst,opt=load(f)[idx]; h=opt-1
    q=QNC(inst,h); v,st=q.decide()
    bounds=[(0,1)]*q.lp.base.N
    res=q.lp.solve(bounds)
    print('idx',idx,'final cuts',len(q.lp.cuts),'root solve status',res.status,
          'cert_fail',st['cert_fail'])
    if res.status==2:
        c,s=farkas_int(q.lp,set())
        print('   root cert?', c is not None, (c or {}).get('scale'))
