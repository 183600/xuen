import sys,json,time
sys.setrecursionlimit(100000)
sys.path[:0]=['exp/v8b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from scl import SCL
from bench_scl import base_corpus
base=base_corpus()
def run(kw,budget):
    yes=nodes=yn=ev=0;t0=time.time()
    for name,idx,inst,opt in base:
        q=SCL(inst,opt,yes_scan=True,yes_node_budget=budget,**kw)
        v,st=q.decide(budget=100,nodecap=5000)
        yes+=v is True; nodes+=st['nodes']; yn+=st['yes_nodes']; ev+=st['scl_evals']
    return yes,nodes,yn,ev,round(time.time()-t0,2)
cfgs={
 'full':{},
 'no_floor':dict(scl_floor=0.0),
 'top1':dict(scl_dfs_top=1),
 'top1_no_floor':dict(scl_dfs_top=1,scl_floor=0.0),
 'top2_no_floor':dict(scl_dfs_top=2,scl_floor=0.0),
 'no_ce_no_floor':dict(scl_alpha=0.0,scl_floor=0.0),
}
for tag,kw in cfgs.items():
    for b in [1000,5000]:
        print(tag,b,run(kw,b),flush=True)
