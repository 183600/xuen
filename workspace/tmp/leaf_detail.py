import sys, pickle
sys.path[:0]=['exp/v71','exp/v61','exp/v60','exp/v13']
from qnc import QNC
from scope import load

def show(tag, inst, h):
    q=QNC(inst,h); v,st=q.decide()
    print(tag,'v',v,'lp',st['lp_solves'],'nodes',st['nodes'],'force',st['force'],
          'sizes',st['leaf_sizes'],'audit',q.audit())
    for F,E,c in q.leaves:
        print('   |F|',len(F),'|E|',len(E),'scale',c['scale'],'beta',len(c['beta']),'dom',len(c['dom']),
              'E',sorted(E)[:8])

rows=load('exp/v20/holdout_cases50.pkl')
show('h5',rows[5][0],rows[5][1]-1)
show('h47',rows[47][0],rows[47][1]-1)
for (name,k,inst,opt,an,al) in pickle.load(open('exp/v71/perturb60.pkl','rb')):
    if (name,k) in [('h5',6),('h5',16),('h47',6),('h47',18),('h47',26)]:
        show(f'{name}-{k}',inst,opt-1)
