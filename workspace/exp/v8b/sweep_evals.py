import sys,time
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
        yes+=v is True;yn+=st['yes_nodes'];ev+=st['scl_evals']
        if v is not True: bad.append((name,idx))
    return yes,yn,ev,round(time.time()-t0,2),bad
basekw=dict(scl_alpha=0.0,scl_floor=0.0,scl_dfs_top=4)
for e1,e2 in [(16,128),(32,192),(32,384),(64,384)]:
    kw=dict(basekw);kw.update(scl_evals1=e1,scl_evals2=e2)
    for b in [1000,5000]:
        print(e1,e2,b,run(kw,b),flush=True)
