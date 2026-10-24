import sys,pickle,time,json
sys.setrecursionlimit(100000)
sys.path[:0]=['exp/v8b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
import numpy as np
from rdf import RDF,check_schedule
from scl import SCL
from qnc import Budget
from ce_proto import load_hard

def getz(inst,h):
 q=RDF(inst,h,yes_scan=True);q.budget=12;q.nodecap=200
 try: q._search([(0,1)]*q.lp.base.N,0)
 except Budget: pass
 if q.root_z is None:
  res=q.lp.solve([(0,1)]*q.lp.base.N)
  if res.status==0: q.root_z=np.array(res.x,copy=True)
 return q.root_z
rows=[]
for name,idx,inst,opt in load_hard():
 z=getz(inst,opt)
 out={'name':name,'idx':idx,'n':inst['n']}
 # RDF constructor
 qr=RDF(inst,opt,yes_scan=True);qr.root_z=z;t=time.time();ok=qr._yes_construct(z,48,4000);dt=time.time()-t
 out['rdf']=dict(ok=ok,t=round(dt,4),yn=qr.yes_nodes,tr=qr.yes_trials_used)
 # SCL constructor
 qs=SCL(inst,opt,yes_scan=True);qs.root_z=z;t=time.time();qs._scl_setup(z);ok=qs._scl_run(384,4000);dt=time.time()-t
 out['scl']=dict(ok=ok,t=round(dt,4),yn=qs.yes_nodes,ev=qs.scl_evals)
 rows.append(out);print(out,flush=True)
json.dump(rows,open('exp/v8b/bench_ctor.json','w'))
for tag in ['rdf','scl']:
 print(tag,'ok',sum(r[tag]['ok'] for r in rows),'t',round(sum(r[tag]['t'] for r in rows),3),'yn',sum(r[tag]['yn'] for r in rows),'trials/evals',sum(r[tag].get('tr',r[tag].get('ev',0)) for r in rows))
