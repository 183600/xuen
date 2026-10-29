import sys,json,time
sys.path[:0]=['exp/v9x','exp/v91','exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from icf import corpora
from sparc import Swarm, _strong_init
rows=list(corpora()); idx={(c,n,i):(c,n,i,inst,k) for c,n,i,inst,k in rows}
sp=json.load(open('exp/v91/bench_sparc.json'))['rows']['strong_pso1_lower']
hard=[r for r in sp if r['known']==r['lb0'] and r['ub_pso']>r['lb0']]
for np_,it in [(8,12),(16,20),(32,40),(64,60)]:
 ok=0; tt=0; ev=0
 for r in hard:
  c,n,i,inst,known=idx[(r['corpus'],r['name'],r['idx'])]
  L,U,s,m,proof,pin=_strong_init(inst)
  sw=Swarm(inst,U,s,m,n_particles=np_,iters=it,seed=7,stall=1000)
  best,st=sw.run()
  cc,s2,m2=best
  tt+=st['t']; ev+=st['evals']
  if cc<=r['lb0']: ok+=1
 print('pso',np_,it,'ok',ok,'/',len(hard),'evals',ev,'t',round(tt,2))
