import sys,pickle,json,time
sys.path[:0]=['exp/v81','exp/v71','exp/v61','exp/v60','exp/v13']
from sqr import SQR
FILES={'holdout50':'exp/v20/holdout_cases50.pkl','synth45':'exp/v28/synth2_45.pkl',
 'large_a':'exp/v14/large_a.pkl','large_b':'exp/v14/large_b.pkl',
 'large_het':'exp/v14/large_het.pkl','hard3':'exp/v13/hard3.pkl','deep8':'exp/v18/deep.pkl'}
def load(f):
    d=pickle.load(open(f,'rb')); return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]
corpus=[]
for name,f in FILES.items():
    for idx,(inst,opt) in enumerate(load(f)): corpus.append((inst,opt-1))
pert=[(inst,opt-1) for (name,k,inst,opt,an,al) in pickle.load(open('exp/v71/perturb60.pkl','rb'))]
stress=[(r['inst'],r['h']) for r in pickle.load(open('exp/v81/h5h47_branch.pkl','rb'))]
cases=corpus+pert+stress
class V1(SQR):
    def _rank(self,z):
        r=super()._rank(z)
        return [(a,b,c,atoms[:1]) for a,b,c,atoms in r]
for name,kw,cls in [('both-atoms',{},SQR),('top1',{},V1),
                    ('top1-2jobs',{'max_candidates':2},V1),
                    ('both-2jobs',{'max_candidates':2},SQR),
                    ('both-gate',{'probe_gate':True},SQR),
                    ('both-cap8',{'probe_cap':8},SQR)]:
    t0=time.time(); lp=nd=0; no=0
    for inst,h in cases:
        x=cls(inst,h,**kw); v,st=x.decide(); lp+=st['lp_solves']; nd+=st['nodes']; no+=v is False
    print(name,'NO',no,'LP',lp,'nodes',nd,'time',round(time.time()-t0,1))
