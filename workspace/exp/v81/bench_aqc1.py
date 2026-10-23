import sys,pickle,json,time
sys.path[:0]=['exp/v81','exp/v71','exp/v61','exp/v60','exp/v13']
from aqc1 import AQC1
from qcc2 import QCC2
from qnc import QNC
FILES={'holdout50':'exp/v20/holdout_cases50.pkl','synth45':'exp/v28/synth2_45.pkl',
 'large_a':'exp/v14/large_a.pkl','large_b':'exp/v14/large_b.pkl',
 'large_het':'exp/v14/large_het.pkl','hard3':'exp/v13/hard3.pkl','deep8':'exp/v18/deep.pkl'}
def load(f):
    d=pickle.load(open(f,'rb')); return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]
corpus=[]; pert=[]
for name,f in FILES.items():
    for idx,(inst,opt) in enumerate(load(f)): corpus.append((name,idx,inst,opt-1))
for (name,k,inst,opt,an,al) in pickle.load(open('exp/v71/perturb60.pkl','rb')): pert.append((name,k,inst,opt-1))
def run(cases):
    rows=[]
    for name,idx,inst,h in cases:
        q=QNC(inst,h); vq,sq=q.decide()
        c=QCC2(inst,h,cut_kind='uniform'); vc,sc=c.decide()
        a=AQC1(inst,h,cut_kind='uniform'); va,sa=a.decide()
        rows.append(dict(name=name,idx=idx,
          q=(sq['lp_solves'],sq['nodes']),c=(sc['lp_solves'],sc['nodes']),
          a=(sa['lp_solves'],sa['nodes']),probes=sa['probes'],pairs=sa['pairs'],
          covers=sc['covers'],why=sa['why'],audit=a.audit(),q_audit=q.audit(),
          force=sa['force'],cover_root=(sa['why']=='cover-root')))
    return rows
t0=time.time()
out={'corpus':run(corpus),'pert':run(pert)}
json.dump(out,open('exp/v81/aqc1_bench.json','w'),indent=1)
for part in out:
    rows=out[part]; print('===',part,len(rows))
    for key in ['q','c','a']:
        print(key,'LP',sum(r[key][0] for r in rows),'nodes',sum(r[key][1] for r in rows))
    print('audit',sum(r['audit'] for r in rows),'q_audit',sum(r['q_audit'] for r in rows))
    print('probes',sum(r['probes'] for r in rows),'cover_root',sum(r['cover_root'] for r in rows))
print('wall',round(time.time()-t0,2))
for r in out['corpus']+out['pert']:
    if r['a']!=(1,1) and not r['cover_root'] and r['a'][0]>2:
        print(r)
