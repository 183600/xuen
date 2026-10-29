import sys,pickle,time,json
sys.setrecursionlimit(100000)
sys.path[:0]=['exp/v8b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from rdf import RDF
from scl import SCL
from bench_rdf import no_corpus
rows=[];t0=time.time()
for ci,(name,idx,inst,h,src) in enumerate(no_corpus()):
 row=dict(name=name,idx=idx,src=src)
 for tag,cls,kw in [('rdf',RDF,dict(yes_scan=True)),('scl',SCL,dict(yes_scan=True))]:
  t=time.time();q=cls(inst,h,**kw);v,st=q.decide(budget=100,nodecap=5000);dt=time.time()-t
  row[tag]=dict(v=v,lp=st['lp_solves'],nodes=st['nodes'],t=round(dt,4),yn=st['yes_nodes'],ev=st.get('scl_evals',0),audit=bool(q.audit_rdf()),pc=bool(q.proof_complete()))
 rows.append(row)
 if ci%50==0: print(ci,flush=True)
json.dump(rows,open('exp/v8b/bench_unified_scl.json','w'))
for tag in ['rdf','scl']:
 agg=dict(no=0,unk=0,yes=0,lp=0,nodes=0,t=0,yn=0,ev=0,audit=0,pc=0)
 for r in rows:
  a=r[tag];agg['no']+=a['v'] is False;agg['unk']+=a['v'] is None;agg['yes']+=a['v'] is True
  agg['lp']+=a['lp'];agg['nodes']+=a['nodes'];agg['t']+=a['t'];agg['yn']+=a['yn'];agg['ev']+=a['ev'];agg['audit']+=a['audit'];agg['pc']+=a['pc']
 print(tag,agg,'wall',round(time.time()-t0,2))
print('scl constructor cases',sum(1 for r in rows if r['scl']['ev']>0))
