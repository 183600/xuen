import sys,pickle,json,time
sys.path[:0]=['exp/v81','exp/v71','exp/v61','exp/v60','exp/v13']
from aqc import AQC
from qcc2 import QCC2
from qnc import QNC
FILES={'holdout50':'exp/v20/holdout_cases50.pkl','synth45':'exp/v28/synth2_45.pkl',
 'large_a':'exp/v14/large_a.pkl','large_b':'exp/v14/large_b.pkl',
 'large_het':'exp/v14/large_het.pkl','hard3':'exp/v13/hard3.pkl','deep8':'exp/v18/deep.pkl'}
def load(f):
    d=pickle.load(open(f,'rb')); return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]
cases=[]
for name,f in FILES.items():
    for idx,(inst,opt) in enumerate(load(f)): cases.append((name,idx,inst,opt-1))
for (name,k,inst,opt,an,al) in pickle.load(open('exp/v71/perturb60.pkl','rb')): cases.append((name,k,inst,opt-1))
rows=[]; t0=time.time()
for name,idx,inst,h in cases:
    q=QNC(inst,h); vq,sq=q.decide()
    c=QCC2(inst,h,cut_kind='uniform'); vc,sc=c.decide()
    a=AQC(inst,h,cut_kind='uniform'); va,sa=a.decide()
    rows.append(dict(name=name,idx=idx,
      q=(sq['lp_solves'],sq['nodes']),c=(sc['lp_solves'],sc['nodes']),
      a=(sa['lp_solves'],sa['nodes']),probes=sa.get('probes',0),
      pairs=sa.get('pairs',0),covers=sa.get('covers',0),
      why=sa.get('why'),audit=a.audit()))
json.dump(rows,open('exp/v81/aqc_bench.json','w'),indent=1)
for key in ['q','c','a']:
    print(key,'NO',sum(r[key][0]>=0 and r[key][1]>0 for r in rows),'LP',sum(r[key][0] for r in rows),'nodes',sum(r[key][1] for r in rows))
print('improved a vs q LP',sum(r['a'][0]<r['q'][0] for r in rows),'worse',sum(r['a'][0]>r['q'][0] for r in rows))
print('probes',sum(r['probes'] for r in rows),'pairs',sum(r['pairs'] for r in rows))
print('wall',round(time.time()-t0,2))
for r in rows:
    if r['a']!=r['q'] or r['probes']:
        print(r)
