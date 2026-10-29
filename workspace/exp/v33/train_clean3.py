import pickle,math,random
TR=pickle.load(open('exp/v33/train3.pkl','rb')); HO=pickle.load(open('exp/v33/holdout3.pkl','rb'))
tr=[x for x in TR if x['hmod']==-1]; ho=[x for x in HO if not x['okf']]
rng=random.Random(11); idx=list(range(len(tr))); rng.shuffle(idx)
va=[tr[i] for i in idx[:300]]; trn=[tr[i] for i in idx[300:]]
D=20
def vec(x): return list(x['x'][:D])
mu=[sum(vec(x)[j] for x in trn)/len(trn) for j in range(D)]
sd=[(sum((vec(x)[j]-mu[j])**2 for x in trn)/len(trn))**0.5 or 1 for j in range(D)]
def norm(x): return [(vec(x)[j]-mu[j])/sd[j] for j in range(D)]
X=[norm(x) for x in trn]; Y=[1 if x['b']<x['f'] else 0 for x in trn]
Xv=[norm(x) for x in va]; Xh=[norm(x) for x in ho]
def mlp(H=8,epochs=200,lr=0.03,seed=1):
    r=random.Random(seed)
    W1=[[r.uniform(-0.5,0.5)/math.sqrt(D) for _ in range(D)] for _ in range(H)]
    b1=[0.0]*H; W2=[r.uniform(-0.5,0.5)/math.sqrt(H) for _ in range(H)]; b2=0.0
    for ep in range(epochs):
        order=list(range(len(X))); r.shuffle(order)
        for ii in order:
            x=X[ii]; y=Y[ii]
            h=[math.tanh(sum(W1[k][j]*x[j] for j in range(D))+b1[k]) for k in range(H)]
            z=sum(W2[k]*h[k] for k in range(H))+b2
            p=1/(1+math.exp(-max(-30,min(30,z)))); dz=p-y
            for k in range(H):
                g=dz*W2[k]*(1-h[k]*h[k])
                for j in range(D): W1[k][j]-=lr*(g*x[j]+1e-3*W1[k][j])
                b1[k]-=lr*g
            for k in range(H): W2[k]-=lr*(dz*h[k]+1e-3*W2[k])
            b2-=lr*dz
    def pred(x):
        h=[math.tanh(sum(W1[k][j]*x[j] for j in range(D))+b1[k]) for k in range(H)]
        z=sum(W2[k]*h[k] for k in range(H))+b2
        return 1/(1+math.exp(-max(-30,min(30,z))))
    return pred,W1,b1,W2,b2
best=None
for H in [6,10]:
  for seed in range(3):
    pred,W1,b1,W2,b2=mlp(H=H,seed=seed)
    for th in [0.3,0.4,0.5,0.6,0.7]:
        tot=sum((x['b'] if pred(z)>th else x['f']) for x,z in zip(va,Xv))
        if best is None or tot<best[0]: best=(tot,H,seed,th)
print('BEST val',best[0],'H',best[1],'seed',best[2],'th',best[3])
H,seed,th=best[1],best[2],best[3]
pred,W1,b1,W2,b2=mlp(H=H,seed=seed)
tot=0;acc=0
for x,z in zip(ho,Xh):
    p=pred(z); c=1 if p>th else 0
    acc+=(c==(1 if x['b']<x['f'] else 0)); tot+=x['b'] if c else x['f']
print('HOLDOUT acc',acc,'tot',tot,'/fwd %.2f'%(37364/tot))

# save best (retrain once)
pred,W1,b1,W2,b2=mlp(H=H,seed=seed)
import json
json.dump(dict(kind='mlp',th=th,mu=mu,sd=sd,W1=W1,b1=b1,W2=W2,b2=b2),open('exp/v33/selector_clean.json','w'))
print('saved selector_clean.json')
