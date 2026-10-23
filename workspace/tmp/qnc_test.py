import sys
sys.path[:0]=['exp/v71','exp/v61','exp/v60','exp/v13']
from qnc import QNC
from scope import load
for idx in [5,47,0,7,21]:
    inst,opt=load('exp/v20/holdout_cases50.pkl')[idx]
    q=QNC(inst,opt-1); v,st=q.decide()
    print('idx',idx,'v',v,'why',st['why'],'lp',st['lp_solves'],'nodes',st['nodes'],
          'prune',st['prunes'],'empty',st['empty_prunes'],'leaves',st['leaves'],
          'force',{i:(len(s)) for i,s in st['force'].items()},'ok',q.audit(),'t',round(st['cert_t'],3))
