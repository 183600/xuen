import sys, json
sys.path[:0]=['exp/v71','exp/v61','exp/v60','exp/v13']
from qnc import QNC
FILES = {'holdout50':'exp/v20/holdout_cases50.pkl','synth45':'exp/v28/synth2_45.pkl',
 'large_a':'exp/v14/large_a.pkl','large_b':'exp/v14/large_b.pkl',
 'large_het':'exp/v14/large_het.pkl','hard3':'exp/v13/hard3.pkl','deep8':'exp/v18/deep.pkl'}
def load(f):
    d=__import__('pickle').load(open(f,'rb'))
    return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]
cases=[(inst,opt-1) for f in FILES.values() for inst,opt in load(f)]
out={}
for b in range(0,10):
    no=sum(QNC(inst,h).decide(budget=b)[0] is False for inst,h in cases)
    out[b]=no; print(b,no,flush=True)
json.dump(out,open('exp/v71/anytime_corpus.json','w'),indent=1)
