import sys, pickle, json
sys.path[:0] = ['exp/v61','exp/v60','exp/v13']
import numpy as np
from alc import ALC
import cert as v60cert

def load(f):
    d=pickle.load(open(f,'rb'))
    return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]

def slacks(inst,h,c,elig_aware):
    n,m,p=inst['n'],inst['m'],inst['p']
    est,q=v60cert.heads_tails(inst,0,[0]*n)
    beta={}
    for k,t,w in c['beta']: beta[(k,t)]=beta.get((k,t),0)+w
    lam={}
    for i,j,t,w in c['dom']: lam[(i,j,t)]=lam.get((i,j,t),0)+w
    out={}
    for i in range(n):
        lo,hi=est[i], h-q[i]-p[i]
        if lo>hi: continue
        for s in range(lo,hi+1):
            val=c['alpha'][i]
            if elig_aware:
                for k in inst['elig'][i]:
                    for u in range(s,min(s+p[i],h)):
                        val+=beta.get((k,u),0)
            else:
                for u in range(s,min(s+p[i],h)): val+=beta.get((None,u),0)
            for j in inst['succ'][i]:
                val-=sum(w for (a,b,t),w in lam.items() if a==i and b==j and t>=s)
            for k2 in inst['pred'][i]:
                val+=sum(w for (a,b,t),w in lam.items() if a==k2 and b==i and t>=s-p[k2])
            out[(i,s)]=val
    return out

def run(f, idx, h):
    inst,opt=load(f)[idx]
    a=ALC(inst,h,cert_on=True)
    rec=[]
    orig=a._extract
    def patched(bounds=None):
        c,ok=orig(bounds)
        if c is None or not ok: return c,ok
        F=set()
        if bounds is not None:
            for cc,bd in enumerate(bounds):
                if bd==(0,0):
                    key=a.lp.cols[cc]; F.add((key[0],key[-1]))
        sl=slacks(inst,h,c,a.elig_aware)
        E={cc for cc in F if sl.get(cc,-1)<0}
        ver= v60cert.verify(inst,h,c,forbid=E,elig_aware=a.elig_aware)
        rec.append(dict(F=len(F),E=len(E),ok=ok,ver_E=ver,
                        beta=len(c['beta']),dom=len(c['dom']),scale=c.get('scale'),
                        obj=c.get('obj')))
        return c,ok
    a._extract=patched
    v,st=a.decide()
    print('idx',idx,'v',v,'nodes',st['nodes'],'lp',st['lp_solves'],'certs',len(rec))
    for r in rec: print('   ',r)
    return rec

for f,idxs in [('exp/v20/holdout_cases50.pkl',[5,47]),('exp/v20/holdout_cases50.pkl',[0,7,21])]:
    d=load(f)
    for i in idxs:
        run(f,i,d[i][1]-1)
