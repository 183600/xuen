import sys,pickle,random,time
sys.path[:0]=['exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13','exp/v8b']
import numpy as np
from rdf import RDF,check_schedule
from qnc import Budget
from ce_proto import rootz,load_hard

def probe(q,dist,seed=0,n=64,cap=50):
    rng=random.Random(seed)
    prom=[]; stats=[]
    for r in range(n):
        rank=q._sample_rank(dist,rng)
        before=q.yes_nodes
        got=q._sgs_dfs(rank,cap,seed=r)
        used=q.yes_nodes-before
        if got is not None: return 'yes',r,used,prom
        stats.append(used)
        if used>=cap: prom.append(rank)
    return 'no',n,stats,prom

if __name__=='__main__':
    for name,idx,inst,opt in load_hard():
        q=rootz(inst,opt); dist=q._lp_distribution(q.root_z)
        t0=time.time(); st,r,used,prom=probe(q,dist,seed=0,n=64,cap=50)
        print(name,idx,'probe',st,'r',r,'used',used,'prom',len(prom),'t',round(time.time()-t0,2))
        if st=='no':
            # try promising with cap 4000
            for pi,rank in enumerate(prom[:8]):
                got=q._sgs_dfs(rank,4000,seed=100+pi)
                print('  prom',pi,'ok',got is not None,'nodes',q.yes_nodes)
                if got is not None: break
