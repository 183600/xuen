import numpy as np, collections, json, time
from scipy.stats import spearmanr
from loader import load_episodes
rng=np.random.default_rng(2); H=10; VEL_LAG=3; K=12
HARD={'PlugInEthernet','Unlock','DisconnectEthernet'}

def build(eps):
    Xs,Ys,gs,grips=[],[],[],[]
    for e in eps:
        X,Y,n=e['X'],e['Y'],e['n']
        if n<=H+VEL_LAG: continue
        V=np.zeros_like(X); V[VEL_LAG:]=X[VEL_LAG:]-X[:-VEL_LAG]
        F=np.concatenate([X,V],1); t=np.arange(VEL_LAG,n-H)
        Xs.append(F[t]); Ys.append(Y[t+H]-Y[t]); gs.append([e['task']]*len(t)); grips.append(X[t,12:14].copy())
    return np.concatenate(Xs),np.concatenate(Ys),np.concatenate(gs),np.concatenate(grips)

def split(eps,frac=0.2):
    bt=collections.defaultdict(list)
    for e in eps: bt[e['task']].append(e)
    tr,te=[],[]
    for t,es in bt.items():
        es=list(es); rng.shuffle(es); n=max(1,int(round(len(es)*frac))); te+=es[:n]; tr+=es[n:]
    return tr,te

def r2(Y,P):
    d=(Y-P)**2; return float(1-d.sum(1).mean()/(Y**2).sum(1).mean())
def per_task_r2(Y,P,g):
    out={}
    for t in np.unique(g):
        m=g==t; out[t]=round(r2(Y[m],P[m]),3)
    return out
def ridge(F,Y,lam=1.0):
    A=np.c_[F,np.ones(len(F))]; W=np.linalg.solve(A.T@A+lam*np.eye(A.shape[1]),A.T@Y); return W
def rp(W,F): return np.c_[F,np.ones(len(F))]@W
def knn(Fb,Yb,Fq):
    Ps,Vs=[],[]
    for s in range(0,len(Fq),500):
        sl=slice(s,s+500); d=((Fq[sl,None]-Fb[None])**2).sum(-1)
        idx=np.argpartition(d,K,1)[:,:K]; dd=np.take_along_axis(d,idx,1)
        sig=np.median(dd[:,-1])+1e-6; w=np.exp(-dd/(2*sig)); w/=w.sum(1,keepdims=True)
        yh=np.einsum('qk,qkd->qd',w,Yb[idx]); Ps.append(yh)
        Vs.append(np.einsum('qk,qkd->qd',w,(Yb[idx]-yh[:,None])**2).sum(1))
    return np.concatenate(Ps),np.concatenate(Vs)

eps=load_episodes(); tr,te=split(eps)
Ftr,Ytr,gtr,grtr=build(tr); Fte,Yte,gte,grte=build(te)
mu,sd=Ftr.mean(0),Ftr.std(0)+1e-6; Ftr=(Ftr-mu)/sd; Fte=(Fte-mu)/sd
Fb,Yb=Ftr[::2],Ytr[::2]; Fq,Yq,gq,grq=Fte[::3],Yte[::3],gte[::3],grte[::3]
W=ridge(Ftr,Ytr); Pr=rp(W,Fq); Pk,Vk=knn(Fb,Yb,Fq)
res={'overall':{'ridge':r2(Yq,Pr),'knn':r2(Yq,Pk),'unc_rho':float(spearmanr(Vk,((Yq-Pk)**2).sum(1)).statistic)}}
for name,mask in [('hard',np.isin(gq,list(HARD))),('contact',(grq.min(1)<1.5)),('free',(grq.min(1)>=1.5))]:
    res[name]={'n':int(mask.sum()),'ridge':round(r2(Yq[mask],Pr[mask]),3),'knn':round(r2(Yq[mask],Pk[mask]),3),
               'unc_rho':round(float(spearmanr(Vk[mask],((Yq[mask]-Pk[mask])**2).sum(1)).statistic),3)}
res['per_task_knn']=per_task_r2(Yq,Pk,gq)
res['per_task_ridge']=per_task_r2(Yq,Pr,gq)
print(json.dumps(res,indent=2))
json.dump(res,open('exp/gear_r2/subset.json','w'),indent=2)
