import sys,json,time
sys.setrecursionlimit(100000)
sys.path[:0]=['exp/v8b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from scl import SCL
from bench_scl import base_corpus
base=base_corpus()
def run(kw,budget):
    yes=yn=ev=0;t0=time.time();bad=[]
    for name,idx,inst,opt in base:
        q=SCL(inst,opt,yes_scan=True,yes_node_budget=budget,**kw)
        v,st=q.decide(budget=100,nodecap=5000)
        yes+=v is True; yn+=st['yes_nodes']; ev+=st['scl_evals']
        if v is not True: bad.append((name,idx,st.get('scl_best_loss')))
    return yes,yn,ev,round(time.time()-t0,2),bad
basekw=dict(scl_alpha=0.0,scl_floor=0.0)
cfgs={
 'A':dict(scl_prior_n=16,scl_prior_pool=16,scl_dfs_top=8,scl_evals1=128,scl_evals2=1024),
 'B':dict(scl_prior_n=32,scl_prior_pool=32,scl_dfs_top=16,scl_evals1=128,scl_evals2=2048),
 'C':dict(scl_prior_n=8,scl_prior_pool=8,scl_dfs_top=1,scl_evals1=256,scl_evals2=2048),
 'D':dict(scl_prior_n=16,scl_prior_pool=16,scl_dfs_top=4,scl_evals1=256,scl_evals2=2048),
}
for tag,cfg in cfgs.items():
    kw=dict(basekw);kw.update(cfg)
    for b in [1000,2000,5000]:
        print(tag,b,run(kw,b),flush=True)
