import sys,time,json
sys.path[:0]=['tmp/ub','exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from hap import weak_rows
from lds_proto import lds
from rdf import check_schedule
rows=weak_rows(4)
for cap,maxd,bud in [(0.02,3,1000),(0.05,3,1500),(0.1,4,3000)]:
 t0=time.time();out=[];nodes=0
 for j,(c,name,idx,inst,known,initial) in enumerate(rows):
  L,U,s,m,proof=initial;best=U
  for D in range(maxd+1):
   if best<=L:break
   r,nd,t=lds(inst,best-1,D,bud,seed=j,time_cap=cap);nodes+=nd
   if r is not None:
    s2,m2=r;c2=max(s2[i]+inst['p'][i] for i in range(inst['n']))
    if c2<best and check_schedule(inst,c2,s2,m2):best=c2
  out.append(best-known)
 print('cap',cap,'maxd',maxd,'bud',bud,'opt',sum(x==0 for x in out),'avg',sum(out)/len(out),'t',round(time.time()-t0,2),'nodes',nodes)
