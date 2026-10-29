import sys, pickle, itertools
sys.path.insert(0,'exp/v13')
import po

def load(path):
    d=pickle.load(open(path,'rb'))
    return [{'inst':x[0],'opt':x[1]} if isinstance(x,tuple) else x for x in d]

class MW:
    def __init__(self,inst,rem,A,est,q,h):
        p=inst['p']; m=inst['m']
        self.tasks=list(po.bititer(rem)); self.m=m
        self.r={i:est[i] for i in self.tasks}; self.d={i:h-q[i] for i in self.tasks}
        self.ps={i:p[i] for i in self.tasks}
        pts=set([0,h])
        for i in self.tasks:
            for v in (self.r[i],self.d[i],self.r[i]+self.ps[i],self.d[i]-self.ps[i]):
                if 0<=v<=h: pts.add(v)
        self.pts=sorted(pts); self.P=len(self.pts)-1
        self.C=[self.pts[c+1]-self.pts[c] for c in range(self.P)]
        self.cap=[sum(max(0,self.pts[c+1]-max(self.pts[c],A[k])) for k in range(m)) for c in range(self.P)]
        # candidate starts per task
        self.cands={}
        for i in self.tasks:
            lo=self.r[i]; hi=self.d[i]-self.ps[i]
            cs=sorted(set([s for s in self.pts if lo<=s<=hi]+[lo,hi]))
            self.cands[i]=cs
    def value(self,x):
        # prefix sums of selected length
        pref=[0]*(self.P+1)
        for c in range(self.P):
            pref[c+1]=pref[c]+(self.C[c] if x[c] else 0)
        tot=0
        for i in self.tasks:
            pi=self.ps[i]; bestv=10**9
            for s in self.cands[i]:
                # overlap with S = pref[at s+p] - pref[at s]
                import bisect
                a=bisect.bisect_right(self.pts,s)-1
                b=bisect.bisect_right(self.pts,s+pi)-1
                v=pref[b]-pref[a]
                if v<bestv: bestv=v
            tot+=bestv
        return tot - sum(self.cap[c] for c in range(self.P) if x[c])
    def ascent(self,x,sweeps=6):
        best=x[:]; bv=self.value(best)
        for _ in range(sweeps):
            improved=False
            for c in range(self.P):
                y=best[:]; y[c]^=1
                v=self.value(y)
                if v>bv: bv=v; best=y; improved=True
            if not improved: break
        return bv,best

six={'hard3#2':('exp/v13/hard3.pkl',2),'hard3#3':('exp/v13/hard3.pkl',3),
 'hard3#5':('exp/v13/hard3.pkl',5),'hard3#10':('exp/v13/hard3.pkl',10),
 'large_a#6':('exp/v14/large_a.pkl',6),'large_het#1':('exp/v14/large_het.pkl',1)}
for name,(path,k) in six.items():
    rec=load(path)[k]; inst=rec['inst']; h=rec['opt']-1; n=inst['n']
    est0,q0=po.heads_tails(inst,0,[0]*n)
    mw=MW(inst,inst['full'],(0,)*inst['m'],tuple(est0),q0,h)
    P=mw.P
    inits=[[1]*P]
    for c in range(P):
        x=[0]*P; x[c]=1; inits.append(x)
    # also pairs of cells adjacent-ish
    best=(-10**9,None)
    for x in inits:
        v,y=mw.ascent(x)
        if v>best[0]: best=(v,y)
    sup=[(mw.pts[c],mw.pts[c+1]) for c in range(P) if best[1][c]]
    print(f"{name} n={n} OPT={rec['opt']} ascent value={best[0]} cells={len(sup)} {sup[:8]}")
