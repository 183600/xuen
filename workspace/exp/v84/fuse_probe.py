"""Probe: can linear fusion of leaf Farkas certificates shrink scopes?"""
import sys, pickle, math
sys.path[:0] = ['exp/v71','exp/v61','exp/v60','exp/v13']
import numpy as np
from qnc import QNC
from cert import _row_meta

FILES = {
 'holdout50': 'exp/v20/holdout_cases50.pkl', 'synth45': 'exp/v28/synth2_45.pkl',
 'large_a': 'exp/v14/large_a.pkl', 'large_b': 'exp/v14/large_b.pkl',
 'large_het': 'exp/v14/large_het.pkl', 'hard3': 'exp/v13/hard3.pkl',
 'deep8': 'exp/v18/deep.pkl'}

def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt'])
            for x in d]

class FQ(QNC):
    def __init__(self,*a,**k):
        super().__init__(*a,**k); self.raw=[]
    def _analyse(self,F):
        got=super()._analyse(F)
        if got is not None: self.raw.append(got[0])
        return got

def dense_y(lp, cert):
    A,hi=lp.matrix(); n=lp.n
    meta=_row_meta(lp.base)+[('dom',i,j,t) for (i,j,t) in lp.cuts]
    y=np.zeros(A.shape[0],dtype=float)
    y[:n]=cert['alpha']
    pos=n
    w={}
    for k,t,v in cert['beta']: w[('cap',k,t)]=w.get(('cap',k,t),0)+v
    for i,j,t,v in cert['dom']: w[('dom',i,j,t)]=w.get(('dom',i,j,t),0)+v
    for i,j,v in cert['exp']: w[('exp',i,j,None)]=w.get(('exp',i,j,None),0)+v
    for r,m in enumerate(meta):
        if m in w: y[n+r]=w[m]
    return y,A,hi

def scope(A,y):
    s=np.asarray(A.T.dot(y)).ravel()
    return s, set(np.where(s<0)[0])

def best_pair(A, y1, y2, tol=1e-9):
    s1=np.asarray(A.T.dot(y1)).ravel(); s2=np.asarray(A.T.dot(y2)).ravel()
    # f(l)=s2+l*(s1-s2); breakpoints where f=0
    ev=[]
    for c in range(len(s1)):
        d=s1[c]-s2[c]
        if abs(d)<1e-18:
            if s2[c]<0: ev.append((0.0,0.0)) # always neg
            continue
        l=-s2[c]/d
        if 0<l<1: ev.append((l,c))
    # sweep: at l=0, neg set = {s2<0}; crossing changes sign
    cnt=sum(1 for v in s2 if v<0)
    best=(cnt,0.0,set(np.where(s2<0)[0]))
    ev.sort()
    # group equal breakpoints
    i=0
    while i<len(ev):
        l=ev[i][0]
        # evaluate midpoint to next event? simpler: after crossing to l+eps, update all at l
        j=i
        while j<len(ev) and abs(ev[j][0]-l)<1e-12: j+=1
        # evaluate just after l
        eps=1e-9
        lam=min(1.0,l+eps) if l<1 else 1.0
        s=lam*s1+(1-lam)*s2
        neg=set(np.where(s<0)[0])
        if len(neg)<best[0]: best=(len(neg),lam,neg)
        i=j
    return best,s1,s2

def js(a,b): return len(a&b),len(a|b)

def run(inst,h,label):
    q=FQ(inst,h); v,st=q.decide()
    if not q.raw: print(label,'no certs',v,st['lp_solves'],st['nodes']); return
    ylist=[]
    for c in q.raw:
        y,A,hi=dense_y(q.lp,c); ylist.append(y)
    # recompute scopes on final A
    scopes=[]
    for y in ylist:
        s,_=scope(A,y); scopes.append(set(np.where(s<0)[0]))
    print(label,'verdict',v,'lp',st['lp_solves'],'nodes',st['nodes'],'leaves',len(ylist),
          'scopes',[len(s) for s in scopes])
    for i in range(len(ylist)):
        for j in range(i+1,len(ylist)):
            (cnt,lam,neg),s1,s2=best_pair(A,ylist[i],ylist[j])
            print('   pair',i,j,'sizes',len(scopes[i]),len(scopes[j]),'best',cnt,
                  'lam',round(lam,3),'inter',len(scopes[i]&scopes[j]),'union',len(scopes[i]|scopes[j]),
                  'negjobs',sorted(set(int(q.lp.cols[z][0]) for z in neg)))

def main():
    cases=[]
    for name,f in FILES.items():
        for idx,(inst,opt) in enumerate(load(f)):
            cases.append((name,idx,inst,opt-1))
    # run all to find branch cases, probe fusion there
    for name,idx,inst,h in cases:
        q=FQ(inst,h); v,st=q.decide()
        if st['nodes']>1 or name in ('holdout50','synth45') and idx in (5,47):
            run(inst,h,f'{name}#{idx}')
    pert=pickle.load(open('exp/v71/perturb60.pkl','rb'))
    for (name,k,inst,opt,an,al) in pert:
        q=FQ(inst,opt-1); v,st=q.decide()
        if st['nodes']>1:
            run(inst,opt-1,f'pert-{name}-{k}')

if __name__=='__main__':
    main()
