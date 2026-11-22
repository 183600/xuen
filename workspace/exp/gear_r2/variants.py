import numpy as np, collections, json, time
from scipy.stats import spearmanr
from scipy.cluster.vq import kmeans2
from loader import load_episodes
rng=np.random.default_rng(1)
H=10; VEL_LAG=3; K=12

def build(eps, feat='absvel'):
    Xs,Ys,gs=[],[],[]
    for e in eps:
        X,Y,n=e['X'],e['Y'],e['n']
        if n<=H+VEL_LAG: continue
        V=np.zeros_like(X); V[VEL_LAG:]=X[VEL_LAG:]-X[:-VEL_LAG]
        grip=X[:,12:14]
        if feat=='absvel': F=np.concatenate([X,V],1)
        elif feat=='vel': F=V
        elif feat=='velgrip': F=np.concatenate([V,grip],1)
        elif feat=='eevel': F=np.concatenate([V[:,:14],grip],1)
        t=np.arange(VEL_LAG,n-H)
        Xs.append(F[t]); Ys.append(Y[t+H]-Y[t]); gs.append([(e['task'],e['ep'])]*len(t))
    return np.concatenate(Xs),np.concatenate(Ys),np.concatenate(gs)

def split(eps,test_tasks=None,frac=0.2):
    if test_tasks is not None:
        return [e for e in eps if e['task'] not in test_tasks],[e for e in eps if e['task'] in test_tasks]
    bt=collections.defaultdict(list)
    for e in eps: bt[e['task']].append(e)
    tr,te=[],[]
    for t,es in bt.items():
        es=list(es); rng.shuffle(es); n=max(1,int(round(len(es)*frac)))
        te+=es[:n]; tr+=es[n:]
    return tr,te

def r2(Y,P): return 1-((Y-P)**2).sum(1).mean()/(Y**2).sum(1).mean()

def predict(Fb,Yb,Fq,penalty=None,K=K):
    Ps,Vs=[],[]
    for s in range(0,len(Fq),500):
        sl=slice(s,s+500)
        d=((Fq[sl,None,:]-Fb[None])**2).sum(-1)
        if penalty is not None: d=d+penalty[sl]
        idx=np.argpartition(d,K,1)[:,:K]; dd=np.take_along_axis(d,idx,1)
        sig=np.median(dd[:,-1])+1e-6
        w=np.exp(-dd/(2*sig)); w/=w.sum(1,keepdims=True)
        yh=np.einsum('qk,qkd->qd',w,Yb[idx])
        Ps.append(yh); Vs.append(np.einsum('qk,qkd->qd',w,(Yb[idx]-yh[:,None,:])**2).sum(1))
    return np.concatenate(Ps),np.concatenate(Vs)

def ridge(F,Y,lam=1.0):
    A=np.c_[F,np.ones(len(F))]; W=np.linalg.solve(A.T@A+lam*np.eye(A.shape[1]),A.T@Y); return W
def rp(W,F): return np.c_[F,np.ones(len(F))]@W

def evaluate(tr,te,feat,softlam=0.0):
    Ftr,Ytr,_=build(tr,feat); Fte,Yte,gte=build(te,feat)
    mu,sd=Ftr.mean(0),Ftr.std(0)+1e-6; Ftr=(Ftr-mu)/sd; Fte=(Fte-mu)/sd
    Fb,Yb=Ftr[::2],Ytr[::2]; Fq,Yq,gq=Fte[::3],Yte[::3],gte[::3]
    W=ridge(Ftr,Ytr)
    res={'feat':feat,'n_q':len(Fq),'ridge':round(r2(Yq,rp(W,Fq)),4),'mean':0.0}
    P,V=predict(Fb,Yb,Fq); res['knn']=round(r2(Yq,P),4)
    res['unc_rho']=round(float(spearmanr(V,((Yq-P)**2).sum(1)).statistic),3)
    # hard gesture
    km=kmeans2(Fb,24,minit='++',seed=0)
    cq=np.argmin(((Fq[:,None]-km[0][None])**2).sum(-1),1)
    pen_hard=np.where(cq[:,None]==km[1][None],0.0,1e9)
    Ph,_=predict(Fb,Yb,Fq,pen_hard); res['gesture_hard']=round(r2(Yq,Ph),4)
    # soft gesture penalty: lam * (0 if same cluster else 1) * median scale
    scale=np.median(((Fq[:50,None]-Fb[None])**2).sum(-1))
    pen_soft=np.where(cq[:,None]==km[1][None],0.0,softlam*scale)
    Ps,_=predict(Fb,Yb,Fq,pen_soft); res['gesture_soft']=round(r2(Yq,Ps),4)
    return res

if __name__=='__main__':
    t0=time.time(); eps=load_episodes(); tr,te=split(eps)
    out=[]
    for feat in ['absvel','vel','velgrip','eevel']:
        out.append(evaluate(tr,te,feat,softlam=0.5))
    print(json.dumps(out,indent=2)); print('elapsed',round(time.time()-t0,1))
    json.dump(out,open('exp/gear_r2/variants_id.json','w'),indent=2)
