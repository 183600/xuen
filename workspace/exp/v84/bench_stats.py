import sys,pickle,json,collections
sys.path[:0]=['exp/v84','exp/v71','exp/v61','exp/v60','exp/v13']
from qrc import QRC
D=pickle.load(open('exp/v81/h5h47_branch.pkl','rb'))
rows=[]; ctr=collections.Counter(); agg=[0,0,0,0,0]
for n,r in enumerate(D):
 q=QRC(r['inst'],r['h']); v,st=q.decide()
 core=q.proof_core(); ctr[(st['why'],st['why_global'],q.conflict[0] if q.conflict else None)]+=1
 rows.append(dict(n=n,src=r['src'],idx=r['idx'],v=v,lp=st['lp_solves'],nodes=st['nodes'],
  why=st['why'],why_global=st['why_global'],conflict=(q.conflict[0] if q.conflict else None),
  core=len(core),leaves=len(q.leaves),steps=st['res_steps'],audit=q.audit(),coreaudit=q.audit_core()))
 agg[0]+=st['lp_solves']; agg[1]+=st['nodes']; agg[2]+=len(core); agg[3]+=len(q.leaves); agg[4]+=int(q.audit_core())
print(ctr)
print('agg lp nodes coreleaves allleaves coreaudit',agg)
print('global proofs',sum(1 for r in rows if r['conflict'] is not None),'of',len(rows))
print('core<all',sum(1 for r in rows if r['core']<r['leaves']))
json.dump(rows,open('exp/v84/stats51.json','w'),indent=1)
