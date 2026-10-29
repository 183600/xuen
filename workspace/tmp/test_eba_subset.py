import sys, json, time
sys.path[:0] = ['exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from eba import run_eba
from hap import weak_rows
rows=list(weak_rows(4))
targets=[('base','holdout',36),('base','large_b',8),('base','large_het',5),('base','large_het',7),('pert','h5',4),('pert','h5',28),('pert','h47',20),('pert','h47',29),('stress','stress',5)]
for c,name,idx,inst,known,init in rows:
    if (c,name,idx) not in targets: continue
    t=time.time()
    r=run_eba(inst,known,name,idx,initial=init,seed=0,lds_nodes=1500,lds_time=0.02,ea_time=0.04,do_ea=False,do_route=False)
    print(c,name,idx,'known',known,'L0',r['L0'],'U0',r['U0'],'probes',r['probes'],'eba_hits',r['eba_hits'],'lds',r['lds_hits'],'ea',r['ea_hits'],'route',r['route_hits'],'work',r['eba_work'],'t',round(r['t'],3),'steps',r['steps'][:6],'ok',r['ok'])
