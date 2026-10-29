import pickle,math,random
TR=pickle.load(open('exp/v33/train3.pkl','rb')); HO=pickle.load(open('exp/v33/holdout3.pkl','rb'))
tr=[x for x in TR if x['hmod']==-1]; ho=[x for x in HO if not x['okf']]
D=25
def vec(x): return list(x['x'])+list(x['p10'])
mu=[sum(vec(x)[j] for x in tr)/len(tr) for j in range(D)]
sd=[(sum((vec(x)[j]-mu[j])**2 for x in tr)/len(tr))**0.5 or 1 for j in range(D)]
def norm(x): return [(vec(x)[j]-mu[j])/sd[j] for j in range(D)]
X=[norm(x) for x in tr]; Y=[1 if x['b']<x['f'] else 0 for x in tr]; Xh=[norm(x) for x in ho]
def logit(epochs=1000,lr=0.08,seed=0):
    rng=random.Random(seed); w=[0.0]*D; b=0.0
    for ep in range(epochs):
        idx=list(range(len(X))); rng.shuffle(idx)
        for ii in idx:
            x=X[ii]; y=Y[ii]; z=sum(w[j]*x[j] for j in range(D))+b
            p=1/(1+math.exp(-max(-30,min(30,z)))); dz=p-y
            for j in range(D): w[j]-=lr*(dz*x[j]+1e-3*w[j])
            b-=lr*dz
    return lambda x: 1/(1+math.exp(-max(-30,min(30,sum(w[j]*x[j] for j in range(D))+b))))
for seed in range(3):
    pred=logit(seed=seed)
    for th in [0.3,0.4,0.5,0.6,0.7]:
        acc=0; tot=0; bwd=0
        for x,z in zip(ho,Xh):
            c=1 if pred(z)>th else 0
            acc += (c==(1 if x['b']<x['f'] else 0)); tot += (x['b'] if c else x['f'])+20; bwd+=c
        print('seed',seed,'th',th,'acc',acc,'bwd',bwd,'total+probe',tot,'/fwd %.2f'%(37364/tot))
