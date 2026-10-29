import sys,json,time
sys.setrecursionlimit(100000)
sys.path[:0]=['exp/v8b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from rdf import RDF,check_schedule
from scl import SCL
from bench_scl import base_corpus

def run(cls,corpus,budget,kw=None):
    yes=unk=nodes=yn=ev=0;t0=time.time();bad=[]
    for name,idx,inst,opt in corpus:
        q=cls(inst,opt,yes_scan=True,yes_node_budget=budget,**(kw or {}))
        v,st=q.decide(budget=100,nodecap=5000)
        yes+=v is True;unk+=v is None;nodes+=st['nodes'];yn+=st['yes_nodes'];ev+=st.get('scl_evals',0)
        if v is not True: bad.append((name,idx))
    return dict(yes=yes,unk=unk,nodes=nodes,yn=yn,ev=ev,t=round(time.time()-t0,2),bad=bad)

if __name__=='__main__':
    base=base_corpus();out=[]
    for b in [1000,2000,5000,10000,20000,60000]:
        r=run(RDF,base,b); s=run(SCL,base,b)
        print('budget',b,'rdf',r['yes'],r['unk'],'yn',r['yn'],'t',r['t'],'| scl',s['yes'],s['unk'],'yn',s['yn'],'ev',s['ev'],'t',s['t'],flush=True)
        out.append(dict(budget=b,rdf=r,scl=s))
    json.dump(out,open('exp/v8b/bench_budget.json','w'))
