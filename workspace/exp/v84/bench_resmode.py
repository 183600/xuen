import sys,pickle,json
sys.path[:0]=['exp/v84','exp/v71','exp/v61','exp/v60','exp/v13']
from qrc import QRC
D=pickle.load(open('exp/v81/h5h47_branch.pkl','rb'))
for name,kw in [('disjoint',dict(disjoint_only=True)),('full',dict(disjoint_only=False))]:
 agg=[0,0,0,0,0]; diffs=[]
 for n,r in enumerate(D):
  q=QRC(r['inst'],r['h'],**kw); v,st=q.decide()
  agg[0]+=int(v is False); agg[1]+=st['lp_solves']; agg[2]+=st['nodes']; agg[3]+=int(bool(q.audit())); agg[4]+=st['res_steps']
  if st['lp_solves']!=317: pass
 print(name,agg)
