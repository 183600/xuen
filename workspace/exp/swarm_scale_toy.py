import numpy as np
rng=np.random.default_rng(7)
OFF=np.array([2.0,2.0])  # distractor cloud centered away from target (0,0)
def sample(K,pg,m=6,R=3.0,sg=.5):
    good=rng.random(K)<pg; A=np.empty((K,2)); ng=int(good.sum())
    if ng: A[good]=rng.normal(0,sg,(ng,2))
    nb=K-ng
    if nb:
        ang=rng.integers(0,m,nb)*(2*np.pi/m)
        c=OFF+R*np.stack([np.cos(ang),np.sin(ang)],1)
        A[~good]=c+rng.normal(0,sg,(nb,2))
    return A
def pick(A,Q,method):
    K=len(A)
    if method=='argmax': return A[np.argmax(Q)]
    if method.startswith('top'):
        frac=float(method[3:-4])/100 if method!='top3mean' else None
        k=3 if method=='top3mean' else max(1,int(np.ceil(K*frac)))
        idx=np.argsort(Q)[-k:]; return A[idx].mean(0)
    if method=='softmax':
        T=max(Q.std(),1e-6); w=np.exp((Q-Q.max())/T); w/=w.sum(); return (w[:,None]*A).sum(0)
    if method=='filt_medoid':
        k=max(1,int(np.ceil(K/2))); idx=np.argsort(Q)[-k:]; S=A[idx]
        d2=((S[:,None,:]-S[None,:,:])**2).sum(-1); return S[np.argmin(d2.sum(1))]
def run(K,pg,sq,methods,n=5000):
    out={m:[0,[]] for m in methods}
    for _ in range(n):
        A=sample(K,pg); Q=-(A**2).sum(1)+rng.normal(0,sq,K)
        for m in methods:
            a=pick(A,Q,m); c=float(a@a); out[m][0]+= c<=1.0; out[m][1].append(c)
    return {m:(out[m][0]/n,np.mean(out[m][1])) for m in methods}
methods=['argmax','softmax','top25mean','top50mean','top3mean','filt_medoid']
print("K,pg,sq,"+",".join(m+"_succ,"+m+"_cost" for m in methods))
for pg in [0.0,0.05,0.1,0.3,0.6]:
  for K in [8,16,32,64]:
    r=run(K,pg,10.0,methods,n=4000)
    vals=[]
    for m in methods: vals += [f"{r[m][0]:.3f}",f"{r[m][1]:.2f}"]
    print(f"{K},{pg},10.0,"+",".join(vals))
