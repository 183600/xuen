"""Prototype: min-conflicts over start-time/machine assignments."""
import sys, pickle, random, time
sys.path[:0]=['exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from rdf import RDF, check_schedule, _heads_latest
from qnc import Budget

def sample_dist(dist,rng):
    s={}
    for i,d in dist.items():
        u=rng.random(); acc=0.0; t=d[-1][0]
        for tt,v in d:
            acc+=v
            if u<=acc: t=tt; break
        s[i]=t
    return s

class Solver:
    def __init__(self,inst,h,dist,seed=0):
        self.inst=inst; self.h=h; self.n=inst['n']; self.m=inst['m']; self.p=inst['p']
        self.dist=dist; self.rng=random.Random(seed)
        self.est, self.q, self.latest=_heads_latest(inst,h)
        self.domain={i:list(range(self.est[i],self.latest[i]+1)) for i in range(self.n)}
    def init(self):
        inst=self.inst; n=self.n; m=self.m
        s=sample_dist(self.dist,self.rng)
        # random eligible machine
        mk=[self.rng.choice(inst['elig'][i]) for i in range(n)]
        load=[[0]*(self.h+1) for _ in range(m)]
        for i in range(n):
            for tt in range(s[i],s[i]+self.p[i]): load[mk[i]][tt]+=1
        return s,mk,load
    def prec_loss(self,s):
        z=0
        for i in range(self.n):
            for j in self.inst['succ'][i]:
                d=s[i]+self.p[i]-s[j]
                if d>0: z+=d
        return z
    def overlap_loss(self,load):
        z=0
        for k in range(self.m):
            for v in load[k]:
                if v>1: z+=v-1
        return z
    def total(self,s,load): return self.prec_loss(s)+self.overlap_loss(load)
    def move_delta(self,s,mk,load,i,t,k):
        om=mk[i]; os=s[i]; p=self.p[i]
        d=0
        # overlap delta: old machine remove
        for tau in range(os,os+p):
            v=load[om][tau]
            d -= max(0,v-1)-max(0,v-2)
        # new machine add
        for tau in range(t,t+p):
            v=load[k][tau]
            d += max(0,v+1-1)-max(0,v-1)
        # precedence delta
        for j in self.inst['pred'][i]:
            d -= max(0,s[j]+self.p[j]-os)
            d += max(0,s[j]+self.p[j]-t)
        for j in self.inst['succ'][i]:
            d -= max(0,os+p-s[j])
            d += max(0,t+p-s[j])
        return d
    def apply(self,s,mk,load,i,t,k):
        om=mk[i]; os=s[i]; p=self.p[i]
        for tau in range(os,os+p): load[om][tau]-=1
        for tau in range(t,t+p): load[k][tau]+=1
        s[i]=t; mk[i]=k
    def violated(self,s,load):
        bad=set()
        for i in range(self.n):
            for j in self.inst['succ'][i]:
                if s[i]+self.p[i]>s[j]: bad.add(i); bad.add(j)
        for k in range(self.m):
            js=sorted([i for i in range(self.n) if mk_global[i]==k],key=lambda i:s[i])
            for a,b in zip(js,js[1:]):
                if s[a]+self.p[a]>s[b]: bad.add(a); bad.add(b)
        return list(bad)
    def run(self,iters=5000,kick_every=60):
        s,mk,load=self.init(); L=self.total(s,load)
        best=(L,dict(s),list(mk))
        # local search with restarts inside
        noimp=0; tabu={}
        for it in range(iters):
            if L==0: return s,mk,it
            # find violated jobs
            bad=[]
            for i in range(self.n):
                for j in self.inst['succ'][i]:
                    if s[i]+self.p[i]>s[j]: bad.append(i); bad.append(j)
            for k in range(self.m):
                js=sorted([i for i in range(self.n) if mk[i]==k],key=lambda i:s[i])
                for a,b in zip(js,js[1:]):
                    if s[a]+self.p[a]>s[b]: bad.append(a); bad.append(b)
            if not bad:
                # should be zero
                if self.prec_loss(s)==0 and self.overlap_loss(load)==0:
                    return s,mk,it
                bad=list(range(self.n))
            i=self.rng.choice(sorted(set(bad)))
            cand=[]
            for t in self.domain[i]:
                for k in self.inst['elig'][i]:
                    if t==s[i] and k==mk[i]: continue
                    if tabu.get(i)==(t,k): continue
                    d=self.move_delta(s,mk,load,i,t,k)
                    cand.append((L+d,self.rng.random(),t,k,d))
            if not cand: continue
            cand.sort(key=lambda x:(x[0],x[1]))
            L2,_,t,k,d=cand[0]
            if L2<=L or self.rng.random()<0.02:
                self.apply(s,mk,load,i,t,k); L=L2
                tabu[i]=(s[i],mk[i])
            else:
                # random kick
                i2=self.rng.randrange(self.n)
                t2=self.rng.choice(self.domain[i2]); k2=self.rng.choice(self.inst['elig'][i2])
                if not (t2==s[i2] and k2==mk[i2]):
                    L+=self.move_delta(s,mk,load,i2,t2,k2)
                    self.apply(s,mk,load,i2,t2,k2)
            if L<best[0]:
                best=(L,dict(s),list(mk)); noimp=0
            else:
                noimp+=1
            if noimp>kick_every:
                # random restart from dist
                s,mk,load=self.init(); L=self.total(s,load); noimp=0; tabu={}
        return (None,None,iters) if best[0]>0 else (best[1],best[2],iters)

mk_global=None

def load_hard():
    D=pickle.load(open('exp/v20/holdout_cases50.pkl','rb'))
    cases=[]
    for idx in [35,39,13,45]:
        inst,opt=D[idx]; cases.append(('holdout',idx,inst,opt))
    for name,f,idxs in [('large_a','exp/v14/large_a.pkl',[5]),('large_het','exp/v14/large_het.pkl',[0,3,7]),('hard3','exp/v13/hard3.pkl',[4]),('large_b','exp/v14/large_b.pkl',[0,1,4])]:
        d=pickle.load(open(f,'rb'))
        for idx in idxs:
            x=d[idx]
            if isinstance(x,dict): inst,opt=x['inst'],x['opt']
            else: inst,opt=x[0],x[1]
            cases.append((name,idx,inst,opt))
    return cases

if __name__=='__main__':
    cases=load_hard()
    for name,idx,inst,opt in cases:
        # use RDF root LP distribution only: run yes_scan=False? need z. Use RDF decide phase A hack
        q=RDF(inst,opt,yes_scan=True)
        # run search small to get root_z
        q.budget=12; q.nodecap=200
        try: q._search([(0,1)]*q.lp.base.N,0)
        except Budget: pass
        if q.root_z is None:
            res=q.lp.solve([(0,1)]*q.lp.base.N)
            if res.status==0: q.root_z=res.x
        dist=q._lp_distribution(q.root_z)
        t0=time.time()
        mk_global={}
        sv=Solver(inst,opt,dist,seed=1)
        # monkey patch violated not used
        s,mk,it=sv.run(iters=4000)
        dt=time.time()-t0
        ok = s is not None and check_schedule(inst,opt,s,mk)
        print(name,idx,'n',inst['n'],'ok',ok,'it',it,'t',round(dt,3))
