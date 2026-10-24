import sys,pickle,random,time
sys.path[:0]=['exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
import numpy as np
from scipy.optimize import linprog
from rdf import RDF, check_schedule
from qnc import Budget

def rootz(inst,opt):
    q=RDF(inst,opt,yes_scan=True); q.budget=12; q.nodecap=200
    try: q._search([(0,1)]*q.lp.base.N,0)
    except Budget: pass
    if q.root_z is None:
        res=q.lp.solve([(0,1)]*q.lp.base.N)
        if res.status==0: q.root_z=np.array(res.x,copy=True)
    return q

def alt_vertices(q, k=8, seed=0, mode='random'):
    rng=np.random.default_rng(seed)
    A,hi=q.lp.matrix(); ne=q.lp.n_eq; N=q.lp.base.N
    out=[]
    for r in range(k):
        if mode=='random': c=rng.normal(size=N)
        elif mode=='early': c=np.array([key[-1] for key in q.lp.cols],float)+rng.normal(scale=1e-3,size=N)
        elif mode=='late': c=-np.array([key[-1] for key in q.lp.cols],float)+rng.normal(scale=1e-3,size=N)
        res=linprog(c,A_ub=A,b_ub=hi,A_eq=A[:ne],b_eq=np.ones(ne),bounds=(0,1),method='highs')
        if res.status==0: out.append(res.x)
    return out

def mix_dist(q, zs):
    n=q.inst['n']; mix={}
    for i in range(n): mix[i]={}
    for z in zs:
        d=q._lp_distribution(z)
        for i in range(n):
            # renormalize per job
            mass=sum(v for t,v in d[i])
            for t,v in d[i]: mix[i][t]=mix[i].get(t,0)+v/mass
    for i in range(n):
        mass=sum(mix[i].values())
        mix[i]=[(t,v/mass) for t,v in sorted(mix[i].items())]
    return mix

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
        base=q._lp_distribution(q.root_z)
        zs=alt_vertices(q,k=8,seed=7,mode='random')
        mix=mix_dist(q,[q.root_z]+zs)
        print(name,idx,'verts',len(zs)+1,'support sizes base',sum(len(v) for v in base.values()),'mix',sum(len(v) for v in mix.values()))
        for tag,dist in [('base',base),('mix',mix)]:
            ok=0; nodes=0; t0=time.time()
            for tr in range(8):
                rng=random.Random(100+tr)
                rank={}
                for i,d in dist.items():
                    u=rng.random(); acc=0.; t=d[-1][0]
                    for tt,v in d:
                        acc+=v
                        if u<=acc: t=tt; break
                    rank[i]=t+rng.random()*1e-6
                got=q._sgs_dfs(rank,4000,seed=tr)
                nodes+=q.yes_nodes
                if got is not None:
                    ok+=1
            print('  ',tag,'ok',ok,'nodes',nodes,'t',round(time.time()-t0,2))
