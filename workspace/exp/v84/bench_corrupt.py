import sys,pickle,json,time
sys.path[:0]=['exp/v84','exp/v71','exp/v61','exp/v60','exp/v13']
from ft import FTQRC
D=pickle.load(open('exp/v81/h5h47_branch.pkl','rb'))
for name,kw in [('corrupt1',dict(corrupt_calls=1)),('corrupt2',dict(corrupt_calls=2))]:
 agg=[0,0,0,0,0,0]
 for r in D:
  q=FTQRC(r['inst'],r['h'],**kw); v,st=q.decide()
  agg[0]+=int(v is False); agg[1]+=st['lp_solves']; agg[2]+=st['nodes']; agg[3]+=int(bool(q.audit())); agg[4]+=st.get('heals',0); agg[5]+=st.get('corrupted',0)
 print(name,dict(no=agg[0],lp=agg[1],nodes=agg[2],audit=agg[3],heals=agg[4],corrupted=agg[5]))
