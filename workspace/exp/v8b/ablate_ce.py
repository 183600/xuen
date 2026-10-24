import sys,pickle,random,time
sys.path[:0]=['exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13','exp/v8b']
import numpy as np
from rdf import RDF,check_schedule
from qnc import Budget
from ce_proto import greedy_rank,rootz,load_hard

def sample_rank(q,prob,dom,rng):
    rank={}
    for i in range(q.inst['n']):
        r=rng.random(); acc=0.; t=dom[i][-1]
        for tt in dom[i]:
            acc+=prob[i].get(tt,0.0)
            if r<=acc: t=tt; break
        rank[i]=t+rng.random()*1e-6
    return rank

def uniform_only(q,h,evals=200,noise=0.10,seed=0):
    rng=random.Random(seed); n=q.inst['n']
    dom={i:sorted({key[-1] for key in q.lp.cols if key[0]==i}) for i in range(n)}
    base=q._lp_distribution(q.root_z)
    prob={}
    for i in range(n):
        u=noise/len(dom[i])
        bd=dict(base[i])
        prob[i]={t:bd.get(t,0.0)*(1-noise)+u for t in dom[i]}
        for t,v in bd.items(): prob[i].setdefault(t,v*(1-noise))
        s=sum(prob[i].values()); prob[i]={t:v/s for t,v in prob[i].items()}
    for e in range(evals):
        rank=sample_rank(q,prob,dom,rng)
        g=greedy_rank(q.inst,rank,None)
        if g is not None and g[2]<=h and check_schedule(q.inst,h,g[0],g[1]):
            return True,e+1
    return False,evals

def ce(q,h,evals=200,K=8,noise=0.05,alpha=0.5,elite_frac=0.25,seed=0,learn=True):
    rng=random.Random(seed); n=q.inst['n']
    dom={i:sorted({key[-1] for key in q.lp.cols if key[0]==i}) for i in range(n)}
    base=q._lp_distribution(q.root_z)
    prior={}
    for i in range(n):
        u=noise/len(dom[i])
        bd=dict(base[i])
        prior[i]={t:bd.get(t,0.0)*(1-noise)+u for t in dom[i]}
        for t,v in bd.items(): prior[i].setdefault(t,v*(1-noise))
        s=sum(prior[i].values()); prior[i]={t:v/s for t,v in prior[i].items()}
    prob={i:dict(prior[i]) for i in range(n)}
    used=0; best=(10**9,None)
    while used<evals:
        samples=[]
        for s in range(min(K,evals-used)):
            rank=sample_rank(q,prob,dom,rng)
            g=greedy_rank(q.inst,rank,None); used+=1
            c=10**9 if g is None else g[2]
            if g is not None and c<=h and check_schedule(q.inst,h,g[0],g[1]):
                return True,used
            samples.append((c,rank))
            if c<best[0]: best=(c,dict(rank))
        if not learn: continue
        samples.sort(key=lambda x:x[0]); ne=max(1,int(len(samples)*elite_frac))
        elite=samples[:ne]
        for i in range(n):
            cnt={t:0.0 for t in dom[i]}
            for c,r in elite:
                t=min(dom[i],key=lambda tt:abs(tt-r[i])); cnt[t]+=1
            tot=sum(cnt.values())
            for t in dom[i]:
                emp=cnt[t]/tot if tot else prior[i][t]
                prob[i][t]=(1-alpha)*prob[i].get(t,0.0)+alpha*(0.5*emp+0.5*prior[i][t])
            ss=sum(prob[i].values())
            for t in dom[i]: prob[i][t]/=ss
    return False,used

if __name__=='__main__':
    for name,idx,inst,opt in load_hard():
        q=rootz(inst,opt)
        r1=uniform_only(q,opt,evals=240,noise=0.10,seed=0)
        r2=ce(q,opt,evals=240,noise=0.05,seed=0,learn=True)
        r3=ce(q,opt,evals=240,noise=0.05,seed=0,learn=False)
        print(name,idx,'uniform',r1,'ce',r2,'no-learn',r3)
