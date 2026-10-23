import pickle, math, random, json
TR=pickle.load(open('exp/v33/train2.pkl','rb'))
HO=pickle.load(open('exp/v33/holdout3.pkl','rb'))
tr=[x for x in TR if x['hmod']==-1]
ho=[x for x in HO if not x['okf']]
D=20
def vec(x): return list(x['x'][:D])
mu=[sum(vec(x)[j] for x in tr)/len(tr) for j in range(D)]
sd=[(sum((vec(x)[j]-mu[j])**2 for x in tr)/len(tr))**0.5 or 1 for j in range(D)]
def norm(x): return [(vec(x)[j]-mu[j])/sd[j] for j in range(D)]
X=[norm(x) for x in tr]; Y=[1 if x['b']<x['f'] else 0 for x in tr]; Xh=[norm(x) for x in ho]

def logit(epochs=1200,lr=0.06,seed=0):
    rng=random.Random(seed); w=[0.0]*D; b=0.0
    for ep in range(epochs):
        idx=list(range(len(X))); rng.shuffle(idx)
        for ii in idx:
            x=X[ii]; y=Y[ii]; z=sum(w[j]*x[j] for j in range(D))+b
            p=1/(1+math.exp(-max(-30,min(30,z)))); dz=p-y
            for j in range(D): w[j]-=lr*(dz*x[j]+1e-3*w[j])
            b-=lr*dz
    return w,b
def mlp(H=6,epochs=250,lr=0.03,seed=1):
    rng=random.Random(seed)
    W1=[[rng.uniform(-0.5,0.5)/math.sqrt(D) for _ in range(D)] for _ in range(H)]
    b1=[0.0]*H; W2=[rng.uniform(-0.5,0.5)/math.sqrt(H) for _ in range(H)]; b2=0.0
    for ep in range(epochs):
        idx=list(range(len(X))); rng.shuffle(idx)
        for ii in idx:
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
    return W1,b1,W2,b2
best=None
for seed in range(3):
    w,b=logit(seed=seed)
    for th in [0.35,0.4,0.45,0.5,0.55,0.6]:
        tot=0; acc=0
        for x,z in zip(ho,Xh):
            c=1 if 1/(1+math.exp(-max(-30,min(30,sum(w[j]*z[j] for j in range(D))+b))))>th else 0
            acc+=(c==(1 if x['b']<x['f'] else 0)); tot+=x['b'] if c else x['f']
        print('logit seed',seed,'th',th,'acc',acc,'tot',tot,'/fwd %.2f'%(37364/tot))
        if best is None or tot<best[0]: best=(tot,'logit',seed,th,w,b)
for seed in range(2):
    W1,b1,W2,b2=mlp(seed=seed)
    for th in [0.35,0.4,0.45,0.5,0.55,0.6]:
        tot=0; acc=0
        for x,z in zip(ho,Xh):
            h=[math.tanh(sum(W1[k][j]*z[j] for j in range(D))+b1[k]) for k in range(6)]
            p=1/(1+math.exp(-max(-30,min(30,sum(W2[k]*h[k] for k in range(6))+b2))))
            c=1 if p>th else 0
            acc+=(c==(1 if x['b']<x['f'] else 0)); tot+=x['b'] if c else x['f']
        print('mlp seed',seed,'th',th,'acc',acc,'tot',tot,'/fwd %.2f'%(37364/tot))
        if tot<best[0]: best=(tot,'mlp',seed,th,W1,b1,W2,b2)
print('BEST',best[0],best[1],best[2],best[3])
json.dump(dict(kind=best[1],seed=best[2],th=best[3],mu=mu,sd=sd,
               w=best[4] if best[1]=='logit' else None,
               b=best[5] if best[1]=='logit' else None,
               W1=best[4] if best[1]=='mlp' else None,
               b1=best[5] if best[1]=='mlp' else None,
               W2=best[6] if best[1]=='mlp' else None,
               b2=best[7] if best[1]=='mlp' else None),open('exp/v33/selector.json','w'))
