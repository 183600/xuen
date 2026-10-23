import pickle, math, random
TR=pickle.load(open('exp/v33/train2.pkl','rb'))
HO=pickle.load(open('exp/v33/holdout_feats.pkl','rb'))
tr=[x for x in TR if x['hmod']==-1]
ho=[x for x in HO if not x['okf']]
D=17
mu=[sum(x['x'][j] for x in tr)/len(tr) for j in range(D)]
sd=[(sum((x['x'][j]-mu[j])**2 for x in tr)/len(tr))**0.5 or 1 for j in range(D)]
def norm(x): return [(x[j]-mu[j])/sd[j] for j in range(D)]
X=[norm(x['x']) for x in tr]; Y=[1 if x['b']<x['f'] else 0 for x in tr]
Xh=[norm(x['x']) for x in ho]
def ev(pred,name):
    acc=0; tot=0
    for x,z in zip(ho,Xh):
        c=1 if pred(z)>0.5 else 0
        acc += (c==(1 if x['b']<x['f'] else 0)); tot += x['b'] if c else x['f']
    oracle=sum(min(x['f'],x['b']) for x in ho); fwd=sum(x['f'] for x in ho)
    print('%-12s acc %2d/50 total %6d  /fwd %.2f  /oracle %.2f'%(name,acc,tot,fwd/tot,tot/oracle))
def logit(epochs=800,lr=0.08,seed=0):
    rng=random.Random(seed); w=[0.0]*D; b=0.0
    for ep in range(epochs):
        idx=list(range(len(X))); rng.shuffle(idx)
        for ii in idx:
            x=X[ii]; y=Y[ii]
            z=sum(w[j]*x[j] for j in range(D))+b
            p=1/(1+math.exp(-max(-30,min(30,z))))
            dz=p-y
            for j in range(D): w[j]-=lr*(dz*x[j]+1e-3*w[j])
            b-=lr*dz
    return lambda x: 1/(1+math.exp(-max(-30,min(30,sum(w[j]*x[j] for j in range(D))+b))))
def mlp(H=8,epochs=300,lr=0.05,seed=1):
    rng=random.Random(seed)
    W1=[[rng.uniform(-0.5,0.5)/math.sqrt(D) for _ in range(D)] for _ in range(H)]
    b1=[0.0]*H; W2=[rng.uniform(-0.5,0.5)/math.sqrt(H) for _ in range(H)]; b2=0.0
    for ep in range(epochs):
        idx=list(range(len(X))); rng.shuffle(idx)
        for ii in idx:
            x=X[ii]; y=Y[ii]
            h=[math.tanh(sum(W1[k][j]*x[j] for j in range(D))+b1[k]) for k in range(H)]
            z=sum(W2[k]*h[k] for k in range(H))+b2
            p=1/(1+math.exp(-max(-30,min(30,z))))
            dz=p-y
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
    return pred
ev(lambda z:0.0,'fwd')
for s in range(3): ev(logit(seed=s),'logit%d'%s)
for H in [4,8]:
    for s in range(2): ev(mlp(H=H,epochs=250,seed=s),'mlp%d/%d'%(H,s))
# trivial feature rules
import statistics
for j,name in [(18,'nsink'),(10,'qmean')]:
    # choose bwd if feature > median
    vals=sorted(x['x'][j] for x in tr); med=vals[len(vals)//2]
    ev(lambda z,j=j: 1.0 if z[j]> (med-mu[j])/sd[j] else 0.0,'rule_'+name)
