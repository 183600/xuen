import sys,pickle,random,time,math
sys.path[:0]=['exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
import numpy as np
from rdf import RDF, check_schedule, _heads_latest, _insert, _earliest
from qnc import Budget

def greedy_rank(inst,rank,latest=None):
    n,m,p=inst['n'],inst['m'],inst['p']
    starts=[None]*n; machs=[None]*n; busy=[[] for _ in range(m)]
    rem=[len(inst['pred'][i]) for i in range(n)]; predfin=[0]*n; done=[False]*n
    for _ in range(n):
        av=[i for i in range(n) if not done[i] and rem[i]==0]
        if not av: return None
        av.sort(key=lambda i:(rank[i],i))
        i=av[0]; base=predfin[i]; best=None
        for k in inst['elig'][i]:
            tt=_earliest(busy[k],base,p[i])
            if latest is not None and tt>latest[i]: continue
            cand=(tt,tt+p[i],k)
            if best is None or cand<best: best=cand
        if best is None: return None
        tt,ft,k=best
        starts[i]=tt; machs[i]=k; done[i]=True; _insert(busy,k,tt,ft)
        for j in inst['succ'][i]:
            predfin[j]=max(predfin[j],ft); rem[j]-=1
    return starts,machs,max(starts[i]+p[i] for i in range(n))

def rootz(inst,opt):
    q=RDF(inst,opt,yes_scan=True); q.budget=12; q.nodecap=200
    try: q._search([(0,1)]*q.lp.base.N,0)
    except Budget: pass
    if q.root_z is None:
        res=q.lp.solve([(0,1)]*q.lp.base.N)
        if res.status==0: q.root_z=np.array(res.x,copy=True)
    return q

def ce_construct(q,h,iters=120,K=8,elite_frac=0.25,alpha=0.5,seed=0,dfs_cap=4000,noise=0.05):
    rng=random.Random(seed)
    inst=q.inst; n=inst['n']; m=inst['m']; p=inst['p']
    est,qq,latest=_heads_latest(inst,h)
    dom={i:sorted({key[-1] for key in q.lp.cols if key[0]==i}) for i in range(n)}
    # prior from root LP
    prior={}
    for i,d in q._lp_distribution(q.root_z).items():
        prior[i]={t:v for t,v in d}
        # add uniform floor over domain
        u=noise/len(dom[i])
        for t in dom[i]: prior[i][t]=prior[i].get(t,0.0)*(1-noise)+u
    prob={i:dict(prior[i]) for i in range(n)}
    best=(10**9,None)
    evals=0
    for it in range(iters):
        samples=[]
        for s in range(K):
            rank={}
            for i in range(n):
                r=rng.random(); acc=0.; t=dom[i][-1]
                for tt in dom[i]:
                    acc+=prob[i].get(tt,0.0)
                    if r<=acc: t=tt; break
                rank[i]=t+rng.random()*1e-6
            g=greedy_rank(inst,rank,latest=None)
            evals+=1
            if g is None: c=10**9
            else:
                starts,machs,c=g
                if c<h+0.5:
                    # verify
                    if check_schedule(inst,h,starts,machs):
                        return starts,machs,evals,it
            samples.append((c,rank))
            if c<best[0]: best=(c,dict(rank))
        samples.sort(key=lambda x:x[0])
        ne=max(1,int(K*elite_frac))
        elite=samples[:ne]
        for i in range(n):
            cnt={t:0.0 for t in dom[i]}
            for c,r in elite:
                # nearest domain label of rank
                t=min(dom[i],key=lambda tt:abs(tt-r[i]))
                cnt[t]+=1.0
            tot=sum(cnt.values())
            for t in dom[i]:
                emp=cnt[t]/tot if tot else prior[i].get(t,0.0)
                prob[i][t]=(1-alpha)*prob[i].get(t,0.0)+alpha*(0.5*emp+0.5*prior[i].get(t,0.0))
            ssum=sum(prob[i].values())
            for t in dom[i]: prob[i][t]/=ssum
        if it%20==19:
            # DFS around best rank
            rem=dfs_cap
            got=q._sgs_dfs(best[1],rem,seed=it)
            if got is not None: return got[0],got[1],evals,it
    # final DFS
    got=q._sgs_dfs(best[1],dfs_cap,seed=999)
    if got is not None: return got[0],got[1],evals,iters
    return None,None,evals,iters

def load_hard():
    D=pickle.load(open('exp/v20/holdout_cases50.pkl','rb'))
    cases=[]
    for idx in [35,39,13,45]:
        inst,opt=D[idx]; cases.append(('holdout',idx,inst,opt))
    for name,f,idxs in [('large_a','exp/v14/large_a.pkl',[5]),('large_het','exp/v14/large_het.pkl',[0,3,7]),('hard3','exp/v13/hard3.pkl',[4]),('large_b','exp/v14/large_b.pkl',[0,1,4])]:
        d=pickle.load(open(f,'rb'))
        for idx in idxs:
            x=d[idx]
            if isinstance(x,dict): inst,opt=x['inst'],x['opt']
            else: inst,opt=x[0],x[1]
            cases.append((name,idx,inst,opt))
    return cases

if __name__=='__main__':
    for name,idx,inst,opt in load_hard():
        q=rootz(inst,opt)
        for seed in [0,1,2]:
            t0=time.time(); s,mk,ev,it=ce_construct(q,opt,iters=120,K=8,seed=seed,dfs_cap=4000)
            ok=s is not None and check_schedule(inst,opt,s,mk)
            print(name,idx,'seed',seed,'ok',ok,'ev',ev,'it',it,'t',round(time.time()-t0,2))
