import sys,json,time
sys.setrecursionlimit(100000)
sys.path[:0]=['exp/v8b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from rdf import RDF
from scl import SCL
from bench_scl import base_corpus

def run(kw,corpus):
    yes=unk=nodes=yn=ev=0;t0=time.time();bad=[]
    for name,idx,inst,opt in corpus:
        q=SCL(inst,opt,yes_scan=True,**kw)
        v,st=q.decide(budget=100,nodecap=5000)
        yes+=v is True;unk+=v is None;nodes+=st['nodes'];yn+=st['yes_nodes'];ev+=st['scl_evals']
        if v is not True: bad.append((name,idx,v))
    return dict(yes=yes,unk=unk,nodes=nodes,yn=yn,ev=ev,t=round(time.time()-t0,2),bad=bad)

if __name__=='__main__':
    base=base_corpus();out={}
    cfgs={
      'full': {},
      'no_ce': dict(scl_alpha=0.0),
      'no_floor': dict(scl_floor=0.0),
      'no_prior': dict(scl_prior_n=0, scl_prior_pool=0),
      'top1': dict(scl_dfs_top=1),
      'top8': dict(scl_dfs_top=8),
      'off': dict(scl_on=False),
    }
    for tag,kw in cfgs.items():
        r=run(kw,base); out[tag]=r
        print(tag,r,flush=True)
    json.dump(out,open('exp/v8b/bench_ablate_scl.json','w'))
