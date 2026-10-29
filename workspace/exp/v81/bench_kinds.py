import sys,pickle,json,time
sys.path[:0]=['exp/v81','exp/v71','exp/v61','exp/v60','exp/v13']
from qcc import QCC
from qcc2 import QCC2
FILES={'holdout50':'exp/v20/holdout_cases50.pkl','synth45':'exp/v28/synth2_45.pkl',
 'large_a':'exp/v14/large_a.pkl','large_b':'exp/v14/large_b.pkl',
 'large_het':'exp/v14/large_het.pkl','hard3':'exp/v13/hard3.pkl','deep8':'exp/v18/deep.pkl'}
def load(f):
    d=pickle.load(open(f,'rb')); return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]
cases=[]
for name,f in FILES.items():
    for idx,(inst,opt) in enumerate(load(f)): cases.append((name,idx,inst,opt-1))
for (name,k,inst,opt,an,al) in pickle.load(open('exp/v71/perturb60.pkl','rb')): cases.append((name,k,inst,opt-1))
for kind in ('uniform','weighted','both'):
    lp=nodes=0; rows=[]; t0=time.time()
    for name,idx,inst,h in cases:
        c=QCC2(inst,h,cut_kind=kind); v,st=c.decide(); lp+=st['lp_solves']; nodes+=st['nodes']
        rows.append((st['lp_solves'],st['nodes'],st['covers'],st['restarts']))
    print(kind,'LP',lp,'nodes',nodes,'time',round(time.time()-t0,2))
