import pickle, math, random, statistics
TR=pickle.load(open('exp/v33/train2.pkl','rb'))
HO=pickle.load(open('exp/v33/holdout_feats.pkl','rb'))
tr=[x for x in TR if x['hmod']==-1]
ho=[x for x in HO[:50]]
# standardize
D=len(tr[0]['x'])
mu=[sum(x['x'][j] for x in tr)/len(tr) for j in range(D)]
sd=[(sum((x['x'][j]-mu[j])**2 for x in tr)/len(tr))**0.5 or 1 for j in range(D)]
def norm(x): return [(v-mu[j])/sd[j] for j,v in enumerate(x)]
X=[norm(x['x']) for x in tr]; Y=[1 if x['b']<x['f'] else 0 for x in tr]
Xh=[norm(x['x']) for x in ho]

def train_mlp(H=10, epochs=600, lr=0.05, seed=1):
    rng=random.Random(seed)
    W1=[[rng.uniform(-0.3,0.3) for _ in range(D)] for _ in range(H)]
    b1=[0.0]*H; W2=[rng.uniform(-0.3,0.3) for _ in range(H)]; b2=0.0
    # momentum
    VW1=[[0.0]*D for _ in range(H)]; Vb1=[0.0]*H; VW2=[0.0]*H; Vb2=0.0
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
                for j in range(D):
                    VW1[k][j]=0.9*VW1[k][j]-lr*(g*x[j]+1e-3*W1[k][j])
                    W1[k][j]+=VW1[k][j]
                Vb1[k]=0.9*Vb1[k]-lr*g; b1[k]+=Vb1[k]
            for k in range(H):
                VW2[k]=0.9*VW2[k]-lr*(dz*h[k]+1e-3*W2[k]); W2[k]+=VW2[k]
            Vb2=0.9*Vb2-lr*dz; b2+=Vb2
    def pred(x):
        h=[math.tanh(sum(W1[k][j]*x[j] for j in range(D))+b1[k]) for k in range(H)]
        z=sum(W2[k]*h[k] for k in range(H))+b2
        return 1/(1+math.exp(-max(-30,min(30,z))))
    return pred

def evaluate(pred,name):
    acc=0; tot=0; best=0
    for x,p in zip(ho,[pred(z) for z in Xh]):
        c = 1 if p>0.5 else 0  # 1=backward
        acc += (c==(1 if x['b']<x['f'] else 0)); tot += x['b'] if c else x['f']
    oracle=sum(min(x['f'],x['b']) for x in ho)
    print('%-10s acc %d/%d total %d  vs_fwd %.2f  vs_oracle %.2f'%(name,acc,len(ho),tot,sum(x['f'] for x in ho)/tot,tot/oracle))

# always forward
evaluate(lambda z:0.0,'fwd')
# logistic regression
def train_logit(epochs=500,lr=0.1):
    w=[0.0]*D; b=0.0; V=[0.0]*D; Vb=0.0
    for ep in range(epochs):
        for x,y in zip(X,Y):
            z=sum(w[j]*x[j] for j in range(D))+b
            p=1/(1+math.exp(-max(-30,min(30,z))))
            dz=p-y
            for j in range(D):
                V[j]=0.9*V[j]-lr*(dz*x[j]+1e-3*w[j]); w[j]+=V[j]
            Vb=0.9*Vb-lr*dz; b+=Vb
    return lambda x: 1/(1+math.exp(-max(-30,min(30,sum(w[j]*x[j] for j in range(D))+b))))
evaluate(train_logit(),'logit')
for H in [4,8,12,20]:
    for seed in [1,2,3]:
        evaluate(train_mlp(H=H,epochs=400,seed=seed),'mlp%d/%d'%(H,seed))
# hand rule nsink
for name,idx,sign in [('nsink',18,1),('qmean',10,-1)]:
    # not used
    pass
