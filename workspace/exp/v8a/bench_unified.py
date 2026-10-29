import sys,pickle,time,json
sys.path[:0]=['exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from rdf import RDF
FILES={'holdout':'exp/v20/holdout_cases50.pkl','synth':'exp/v28/synth2_45.pkl','large_a':'exp/v14/large_a.pkl','large_b':'exp/v14/large_b.pkl','large_het':'exp/v14/large_het.pkl','hard3':'exp/v13/hard3.pkl','deep':'exp/v18/deep.pkl'}
def load(f):
 d=pickle.load(open(f,'rb')); return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]
rows=[]
for name,f in FILES.items():
 for idx,(inst,opt) in enumerate(load(f)):
  rows.append((name,idx,inst,opt-1,'base'))
for (name,k,inst,opt,an,al) in pickle.load(open('exp/v71/perturb60.pkl','rb')):
 rows.append((name,k,inst,opt-1,'pert'))
for r in pickle.load(open('exp/v81/h5h47_branch.pkl','rb')):
 rows.append(('stress',r['idx'],r['inst'],r['h'],'stress'))
t0=time.time(); out=[]
for k,(name,idx,inst,h,src) in enumerate(rows):
 q=RDF(inst,h,yes_scan=True); v,st=q.decide(budget=100,nodecap=5000)
 out.append(dict(name=name,idx=idx,src=src,v=v,lp=st['lp_solves'],nodes=st['nodes'],calls=st['yes_calls'],trials=st['yes_trials'],ynodes=st['yes_nodes'],why=st['why'],audit=q.audit_rdf(),pc=q.proof_complete()))
print('TOTAL t',round(time.time()-t0,2),'NO',sum(r['v'] is False for r in out),'UNK',sum(r['v'] is None for r in out),'YES',sum(r['v'] is True for r in out))
print('lp',sum(r['lp'] for r in out),'nodes',sum(r['nodes'] for r in out),'calls',sum(r['calls'] for r in out),'trials',sum(r['trials'] for r in out),'ynodes',sum(r['ynodes'] for r in out))
print('calls>0',sum(1 for r in out if r['calls']))
for src in ['base','pert','stress']:
 rr=[r for r in out if r['src']==src]
 print(src,len(rr),'NO',sum(r['v'] is False for r in rr),'lp',sum(r['lp'] for r in rr),'nodes',sum(r['nodes'] for r in rr),'trials',sum(r['trials'] for r in rr),'ynodes',sum(r['ynodes'] for r in rr))
print('worst ynodes')
for r in sorted(out,key=lambda r:-r['ynodes'])[:8]: print(r)
json.dump(out,open('exp/v8a/bench_unified_no.json','w'))
