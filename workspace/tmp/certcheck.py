import sys, pickle
sys.path[:0]=['exp/v71','exp/v61','exp/v60','exp/v13']
from qnc import QNC
FILES = {'holdout50':'exp/v20/holdout_cases50.pkl','synth45':'exp/v28/synth2_45.pkl',
 'large_a':'exp/v14/large_a.pkl','large_b':'exp/v14/large_b.pkl',
 'large_het':'exp/v14/large_het.pkl','hard3':'exp/v13/hard3.pkl','deep8':'exp/v18/deep.pkl'}
def load(f):
    d=pickle.load(open(f,'rb'))
    return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]
cases=[(inst,opt-1) for f in FILES.values() for inst,opt in load(f)]
cases += [(inst,opt-1) for (n,k,inst,opt,an,al) in pickle.load(open('exp/v71/perturb60.pkl','rb'))]
calls=fails=leaves=0; scales=[]
for inst,h in cases:
    q=QNC(inst,h); v,st=q.decide()
    calls+=st['cert_calls']; fails+=st['cert_fail']; leaves+=st['leaves']
    for F,E,c in q.leaves: scales.append(c['scale'])
print('cases',len(cases),'calls',calls,'fails',fails,'leaves',leaves,
      'scale_med',sorted(scales)[len(scales)//2],'scale_max',max(scales),'nscale',len(scales))
