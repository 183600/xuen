import sys,pickle,json
sys.path[:0]=['exp/v81','exp/v71','exp/v61','exp/v60','exp/v13']
from qnc import QNC
from sqr import SQR
FILES={'holdout50':'exp/v20/holdout_cases50.pkl','synth45':'exp/v28/synth2_45.pkl',
 'large_a':'exp/v14/large_a.pkl','large_b':'exp/v14/large_b.pkl',
 'large_het':'exp/v14/large_het.pkl','hard3':'exp/v13/hard3.pkl','deep8':'exp/v18/deep.pkl'}
def load(f):
    d=pickle.load(open(f,'rb')); return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]
cases=[]
for name,f in FILES.items():
    for idx,(inst,opt) in enumerate(load(f)): cases.append((inst,opt-1))
for (name,k,inst,opt,an,al) in pickle.load(open('exp/v71/perturb60.pkl','rb')): cases.append((inst,opt-1))
out={}
for budget in range(0,9):
    row={}
    for tag,cls in [('q',QNC),('s',SQR)]:
        no=aud=splits=probes=0
        for inst,h in cases:
            x=cls(inst,h); v,st=x.decide(budget=budget)
            if v is False:
                no+=1
                if x.audit(): aud+=1
            splits+=st.get('splits',0); probes+=st.get('probes',0)
        row[tag]=dict(no=no,audit=aud,splits=splits,probes=probes)
    out[budget]=row
    print(budget,row,flush=True)
json.dump(out,open('exp/v81/anytime_sqr.json','w'),indent=1)
