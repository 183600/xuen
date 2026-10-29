import sys,pickle,json,time,collections
sys.path[:0]=['exp/v84','exp/v71','exp/v61','exp/v60','exp/v13']
from qnc import QNC
from qrc import QRC
FILES={'holdout50':'exp/v20/holdout_cases50.pkl','synth45':'exp/v28/synth2_45.pkl',
 'large_a':'exp/v14/large_a.pkl','large_b':'exp/v14/large_b.pkl',
 'large_het':'exp/v14/large_het.pkl','hard3':'exp/v13/hard3.pkl','deep8':'exp/v18/deep.pkl'}
def load(f):
 d=pickle.load(open(f,'rb')); return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]
out={}
for tag,cases in [('corpus',[(n,i,inst,opt-1) for n,f in FILES.items() for i,(inst,opt) in enumerate(load(f))]),
                  ('pert',[(n,k,inst,opt-1) for (n,k,inst,opt,an,al) in pickle.load(open('exp/v71/perturb60.pkl','rb'))])]:
 rows=[]; agg={'qnc':[0,0,0,0],'qrc':[0,0,0,0]}; ctr=collections.Counter()
 for name,idx,inst,h in cases:
  t0=time.time(); a=QNC(inst,h); va,sa=a.decide(); ta=time.time()-t0
  t0=time.time(); b=QRC(inst,h); vb,sb=b.decide(); tb=time.time()-t0
  core=b.proof_core()
  row=dict(name=name,idx=idx,h=h,
   q_v=va,q_lp=sa['lp_solves'],q_nodes=sa['nodes'],q_t=ta,q_audit=a.audit(),
   r_v=vb,r_lp=sb['lp_solves'],r_nodes=sb['nodes'],r_t=tb,r_audit=b.audit(),
   r_core=b.audit_core(),core=len(core),leaves=len(b.leaves),
   conflict=(b.conflict[0] if b.conflict else None),why=sb['why'],
   why_global=sb['why_global'],res_steps=sb['res_steps'],units=sb['res_units'])
  rows.append(row)
  for k,v,s,au in [('qnc',va,sa,a.audit()),('qrc',vb,sb,b.audit())]:
   agg[k][0]+=int(v is False); agg[k][1]+=s['lp_solves']; agg[k][2]+=s['nodes']; agg[k][3]+=int(bool(au))
  ctr[(row['why'],row['why_global'],row['conflict'])]+=1
 print(tag,'agg',agg,'ctr',ctr)
 out[tag]=dict(rows=rows,agg=agg,ctr={str(k):v for k,v in ctr.items()})
# branch 51
D=pickle.load(open('exp/v81/h5h47_branch.pkl','rb'))
rows=[]; agg={'qnc':[0,0,0,0],'qrc':[0,0,0,0]}; ctr=collections.Counter()
for n,r in enumerate(D):
 inst,h=r['inst'],r['h']
 a=QNC(inst,h); va,sa=a.decide(); b=QRC(inst,h); vb,sb=b.decide()
 core=b.proof_core()
 rows.append(dict(n=n,src=r['src'],idx=r['idx'],
  q_v=va,q_lp=sa['lp_solves'],q_nodes=sa['nodes'],q_audit=a.audit(),
  r_v=vb,r_lp=sb['lp_solves'],r_nodes=sb['nodes'],r_audit=b.audit(),
  r_core=b.audit_core(),core=len(core),leaves=len(b.leaves),
  conflict=(b.conflict[0] if b.conflict else None),why=sb['why'],
  why_global=sb['why_global'],res_steps=sb['res_steps'],units=sb['res_units']))
 for k,v,s,au in [('qnc',va,sa,a.audit()),('qrc',vb,sb,b.audit())]:
  agg[k][0]+=int(v is False); agg[k][1]+=s['lp_solves']; agg[k][2]+=s['nodes']; agg[k][3]+=int(bool(au))
 ctr[(rows[-1]['why'],rows[-1]['why_global'],rows[-1]['conflict'])]+=1
print('branch51','agg',agg,'ctr',ctr,'core',sum(r['core'] for r in rows),'leaves',sum(r['leaves'] for r in rows))
out['branch51']=dict(rows=rows,agg=agg,ctr={str(k):v for k,v in ctr.items()})
json.dump(out,open('exp/v84/final.json','w'),indent=1)
