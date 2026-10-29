import sys,pickle,json
sys.path[:0]=['exp/v84','exp/v71','exp/v61','exp/v60','exp/v13']
from qnc import QNC
from qrc import QRC
D=pickle.load(open('exp/v81/h5h47_branch.pkl','rb'))
out={}
for k in range(0,11):
 row={}
 for name,cls in [('qnc',QNC),('qrc',QRC)]:
  no=aud=coreaud=lp=nodes=0
  for r in D:
   q=cls(r['inst'],r['h']); v,s=q.decide(budget=k)
   if v is False:
    no+=1
    if q.audit(): aud+=1
    try:
     if q.audit_core(): coreaud+=1
    except Exception: pass
   lp+=s['lp_solves']; nodes+=s['nodes']
  row[name]=dict(no=no,audit=aud,coreaudit=coreaud,lp=lp,nodes=nodes)
 out[k]=row
 print(k,row,flush=True)
json.dump(out,open('exp/v84/anytime51.json','w'),indent=1)
