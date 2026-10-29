import sys,pickle,time,json
sys.setrecursionlimit(100000)
sys.path[:0]=['exp/v8b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from rdf import RDF,check_schedule
from scl import SCL
from bench_scl import base_corpus,pert_corpus

def run(kw,corpus):
    yes=unk=nodes=yn=ev=0;t0=time.time();bad=[]
    for name,idx,inst,opt in corpus:
        q=SCL(inst,opt,yes_scan=True,**kw)
        v,st=q.decide(budget=100,nodecap=5000)
        yes+=v is True; unk+=v is None; nodes+=st['nodes']; yn+=st['yes_nodes']; ev+=st['scl_evals']
        if v is not True: bad.append((name,idx,v,st.get('scl_best_loss')))
    return dict(yes=yes,unk=unk,nodes=nodes,yn=yn,ev=ev,t=round(time.time()-t0,2),bad=bad)

if __name__=='__main__':
    base=base_corpus(); pert=pert_corpus()
    for e1,e2 in [(16,128),(32,192),(32,256),(64,384)]:
        kw=dict(scl_evals1=e1,scl_evals2=e2)
        r1=run(kw,base); r2=run(kw,pert)
        print('cfg',e1,e2,'base',r1['yes'],r1['unk'],'yn',r1['yn'],'ev',r1['ev'],'t',r1['t'],'| pert',r2['yes'],r2['unk'],'yn',r2['yn'],'ev',r2['ev'],'t',r2['t'])
        if r1['bad']: print(' bad',r1['bad'][:5])
