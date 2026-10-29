import sys, time, math
sys.path[:0]=['exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
import numpy as np, scipy.sparse as sp
from scipy.optimize import linprog
from sdecc import SDLP
from cert import integer_certificate, verify, _farkas_lp
from po import heads_tails
from sage import _elig_aware
from pact import _integral_schedule, _singleton_leaf

# ---------------- proof objects
class CoreProof:
    kind='core'
    def __init__(self, inst, h, core):
        self.inst, self.h, self.core = inst, h, frozenset(core)
    def audit_rdf(self):
        return True
    def proof_complete(self):
        return self.audit_rdf()

class LeafProof(CoreProof):
    kind='core-leaf'
    def __init__(self,inst,h,core,cert):
        super().__init__(inst,h,core); self.cert=cert
    def audit_rdf(self):
        return bool(self.cert is not None and
                    verify(self.inst,self.h,self.cert,forbid=self.core))

class EmptyProof(CoreProof):
    kind='core-empty'
    def __init__(self,inst,h,job,core):
        super().__init__(inst,h,core); self.job=job
    def audit_rdf(self):
        if not (0<=self.job<self.inst['n']): return False
        est,q=heads_tails(self.inst,0,[0]*self.inst['n'])
        dom=set(range(est[self.job],self.h-q[self.job]-self.inst['p'][self.job]+1))
        times={t for (j,t) in self.core if j==self.job}
        return dom <= times

class ComposeProof(CoreProof):
    kind='core-compose'
    def __init__(self,inst,h,F,i,L,R,left,right):
        self.F=frozenset(F); self.i=i; self.L=frozenset(L); self.R=frozenset(R)
        self.left=left; self.right=right
        core=(left.core - {(i,t) for t in self.L}) | (right.core - {(i,t) for t in self.R})
        super().__init__(inst,h,core)
    def audit_rdf(self):
        try:
            if self.left.h!=self.h or self.right.h!=self.h: return False
            if not self.left.audit_rdf() or not self.right.audit_rdf(): return False
            if self.L & self.R: return False
            if not self.L or not self.R: return False
            if not self.left.core <= (self.F | {(self.i,t) for t in self.L}): return False
            if not self.right.core <= (self.F | {(self.i,t) for t in self.R}): return False
            core=(self.left.core - {(self.i,t) for t in self.L}) | (self.right.core - {(self.i,t) for t in self.R})
            return core == self.core and self.core <= self.F
        except Exception:
            return False

class ResolveProof(CoreProof):
    kind='core-resolve'
    def __init__(self,inst,h,pivot,c1,c2):
        self.pivot=pivot; self.c1=c1; self.c2=c2
        d1=clause(c1.core); d2=clause(c2.core)
        inter=d1.get(pivot,frozenset()) & d2.get(pivot,frozenset())
        out={}
        for d in (d1,d2):
            for j,S in d.items():
                if j!=pivot: out[j]=out.get(j,frozenset())|S
        if inter: out[pivot]=inter
        core=frozenset((j,t) for j,S in out.items() for t in S)
        super().__init__(inst,h,core)
    def audit_rdf(self):
        try:
            if not self.c1.audit_rdf() or not self.c2.audit_rdf(): return False
            d1=clause(self.c1.core); d2=clause(self.c2.core)
            if self.pivot not in d1 or self.pivot not in d2: return False
            inter=d1[self.pivot] & d2[self.pivot]
            out={}
            for d in (d1,d2):
                for j,S in d.items():
                    if j!=self.pivot: out[j]=out.get(j,frozenset())|S
            if inter: out[self.pivot]=inter
            core=frozenset((j,t) for j,S in out.items() for t in S)
            return core==self.core
        except Exception:
            return False

class ForceProof(CoreProof):
    kind='core-force'
    def __init__(self,inst,h,F,i,force_lits,clause_proof,child):
        self.F=frozenset(F); self.i=i; self.force_lits=frozenset(force_lits)
        self.clause_proof=clause_proof; self.child=child
        C=clause(clause_proof.core)
        Cother=frozenset((j,t) for j,S in C.items() if j!=i for t in S)
        core=(child.core - self.force_lits) | Cother
        super().__init__(inst,h,core)
    def audit_rdf(self):
        try:
            if not self.clause_proof.audit_rdf() or not self.child.audit_rdf(): return False
            C=clause(self.clause_proof.core)
            if self.i not in C: return False
            Cother=frozenset((j,t) for j,S in C.items() if j!=self.i for t in S)
            if not Cother <= self.F: return False
            if self.force_lits & self.F: return False
            # all forced literals are for job i and outside its clause literal
            if any(j!=self.i for j,t in self.force_lits): return False
            if not self.child.core <= (self.F | self.force_lits): return False
            core=(self.child.core - self.force_lits) | Cother
            return core==self.core and self.core <= self.F
        except Exception:
            return False

def clause(core):
    d={}
    for i,t in core: d.setdefault(i,set()).add(t)
    return {i:frozenset(S) for i,S in d.items()}

# ---------------- full LP for supports
class FullLP:
    def __init__(self, inst,h,elig):
        self.inst,self.h,self.elig=inst,h,elig
        est,q=heads_tails(inst,0,[0]*inst['n'])
        self.lp=SDLP(inst,h,est,q,use_dom=True,elig_aware=elig,forbid=None)
        self.by={}
        for c,key in enumerate(self.lp.cols):
            self.by.setdefault((key[0],key[-1]),[]).append(c)
        self.items=sorted(self.by)
    def support(self,F,tol=1e-8):
        rows=[]
        present=[]
        for it in self.items:
            if it in F:
                row=np.zeros(self.lp.N); row[self.by[it]]=1.0
                rows.append(sp.csr_matrix(row)); present.append(it)
        if not rows: return None,None
        A2=sp.vstack([self.lp.A]+rows).tocsr()
        hi2=np.concatenate([self.lp.hi,np.zeros(len(rows))])
        class V: pass
        v=V(); v.A,v.hi,v.n_eq,v.N=A2,hi2,self.lp.n_eq,self.lp.N
        r=_farkas_lp(v)
        if r.status!=0 or r.fun>=0: return None,None
        base=self.lp.A.shape[0]-self.lp.n_eq
        core=[]
        for k,it in enumerate(present):
            if abs(r.x[self.lp.n_eq+base+k])>tol: core.append(it)
        return frozenset(core),present

def leaf_core(inst,h,F,elig,full,stats):
    est,q=heads_tails(inst,0,[0]*inst['n'])
    # empty-domain rule first: cheapest and exact
    for i in range(inst['n']):
        dom=set(range(est[i],h-q[i]-inst['p'][i]+1))
        Fi=frozenset((i,t) for (j,t) in F if j==i)
        if dom <= {t for (_,t) in Fi}:
            stats['empty']=stats.get('empty',0)+1
            return EmptyProof(inst,h,i,Fi)
    C,present=full.support(F)
    if C is not None:
        stats['support_calls']+=1
        cert=integer_certificate(inst,h,use_dom=True,elig_aware=elig,forbid=C)
        if cert is not None and verify(inst,h,cert,forbid=C):
            stats['support_ok']+=1
            return LeafProof(inst,h,C,cert)
    stats['support_fail']+=1
    stats.setdefault('s_fail_F',[]).append(frozenset(F))
    C=frozenset(F)
    cert=integer_certificate(inst,h,use_dom=True,elig_aware=elig,forbid=C)
    if cert is not None and verify(inst,h,cert,forbid=C):
        return LeafProof(inst,h,C,cert)
    stats.setdefault('fail_F',[]).append((len(F), sorted(F)[:8]))
    return None

# ---------------- clause database
class DB:
    def __init__(self,inst,h,use_res=True,max_clauses=512,max_res=128):
        self.inst,self.h=inst,h
        self.items=[]   # (core,proof)
        self.use_res=use_res; self.max_clauses=max_clauses; self.max_res=max_res
        self.steps=0
        self.global_proof=None
    def _subsumes(self,A,B):
        dA=clause(A); dB=clause(B)
        return set(dA)<=set(dB) and all(S<=dB[i] for i,S in dA.items())
    def add(self,p):
        if p.core in ():
            pass
        if not p.core:
            self.global_proof=p
            return True
        # existing subsumes new -> drop
        for C,_ in self.items:
            if self._subsumes(C,p.core): return False
        # new subsumes existing -> remove
        self.items=[(C,q) for C,q in self.items if not self._subsumes(p.core,C)]
        if len(self.items)>=self.max_clauses: return False
        self.items.append((p.core,p))
        if self.use_res: self._resolve_new(len(self.items)-1)
        return True
    def _resolve_new(self,idx):
        if self.global_proof is not None: return
        c1,p1=self.items[idx]
        d1=clause(c1)
        steps=0
        i=0
        while i<len(self.items) and steps<self.max_res and self.global_proof is None:
            if i==idx: i+=1; continue
            c2,p2=self.items[i]; d2=clause(c2)
            for j in set(d1)&set(d2):
                if d1[j] & d2[j]: continue
                rp=ResolveProof(self.inst,self.h,j,p1,p2)
                steps+=1; self.steps+=1
                if not rp.core:
                    self.global_proof=rp
                    break
                if any(self._subsumes(C,rp.core) for C,_ in self.items):
                    continue
                self.items=[(C,q) for C,q in self.items if not self._subsumes(rp.core,C)]
                self.items.append((rp.core,rp))
                if len(self.items)>=self.max_clauses: break
            i+=1
        # do not recursively saturate
    def find_falsified(self,F):
        for C,p in self.items:
            if C <= F: return p
        return None
    def find_unit(self,F,dom):
        # return (clause_proof, job, forced_literals) for a unit clause
        for C,p in self.items:
            d=clause(C)
            bad=[]
            for i,S in d.items():
                Fi={t for (j,t) in F if j==i}
                if not (S <= Fi):
                    if (dom[i]-Fi) & S:
                        bad.append(i)
                    else:
                        bad.append('falsified')
            if len(bad)==1 and bad[0]!='falsified':
                i=bad[0]; Fi={t for (j,t) in F if j==i}
                Sdom=d[i] & (dom[i]-Fi)
                if Sdom and Sdom != (dom[i]-Fi):
                    forced=frozenset((i,t) for t in (dom[i]-Fi-Sdom))
                    return p,i,forced
        return None
    def find_guide(self,F,dom):
        best=None
        for C,p in self.items:
            d=clause(C)
            # satisfied if some job's allowed times all inside literal
            sat=False; choices=[]
            for i,S in d.items():
                allowed=dom[i]-{t for (j,t) in F if j==i}
                if allowed and allowed<=S: sat=True; break
                inter=allowed & S
                if inter and inter!=allowed:
                    choices.append((len(inter),i,inter,allowed-inter))
            if sat: continue
            if choices:
                choices.sort()
                cand=(choices[0],p)
                if best is None or cand[0][0]<best[0][0]: best=cand
        return best

# ---------------- search
def choose_frac(lp,z,bounds,inst,q):
    n=inst['n']; cand=[]
    for i in range(n):
        times=sorted({key[-1] for c,key in enumerate(lp.cols) if key[0]==i and bounds[c]!=(0,0)})
        if len(times)<=1: continue
        dist=[]
        for tt in times:
            v=sum(z[c] for c,key in enumerate(lp.cols) if key[0]==i and key[-1]==tt and bounds[c]!=(0,0))
            dist.append((tt,v))
        frac=sum(v for _,v in dist if 1e-7<v<1-1e-7)
        if frac<=1e-7: continue
        cand.append(((sum(v for _,v in dist),q[i],len(inst['succ'][i]),-i),i,dist))
    if not cand: return None,None,None
    cand.sort(reverse=True); _,i,dist=cand[0]
    total=sum(v for _,v in dist); acc=0; mid=dist[0][0]
    for tt,v in dist:
        acc+=v
        if acc>=0.5*total: mid=tt; break
    times=[tt for tt,_ in dist]; lo=[tt for tt in times if tt>mid]; hi=[tt for tt in times if tt<=mid]
    if not lo or not hi:
        mid=times[len(times)//2-1]; lo=[tt for tt in times if tt>mid]; hi=[tt for tt in times if tt<=mid]
    if not lo or not hi: return None,None,None
    return i,lo,hi

def bounds_from_F(lp,F):
    b=[(0,1)]*lp.N
    for c,key in enumerate(lp.cols):
        if (key[0],key[-1]) in F: b[c]=(0,0)
    return b

def bounds_from_sets(lp,bounds,i,L):
    b=list(bounds); L=set(L)
    for c,key in enumerate(lp.cols):
        if key[0]==i and key[-1] not in L: b[c]=(0,0)
    return b

def core_decide(inst,h,use_clauses=True,use_res=True,use_guide=False,use_force=True,
                max_clauses=512,max_res=128,max_nodes=None,seed=0):
    t0=time.time()
    n=inst['n']; elig=_elig_aware(inst)
    est,q=heads_tails(inst,0,[0]*n)
    lp=SDLP(inst,h,est,q,use_dom=True,elig_aware=elig)
    full=FullLP(inst,h,elig)
    base=[(0,1)]*lp.N
    dom={}
    for i in range(n): dom[i]=set(range(est[i],h-q[i]-inst['p'][i]+1))
    db=DB(inst,h,use_res=use_res,max_clauses=max_clauses,max_res=max_res)
    stats=dict(nodes=0,lp=0,cert=0,support_calls=0,support_ok=0,support_fail=0,
               clauses=0,res_steps=0,backjumps=0,guides=0,depth=0,unknown=False,leaf=0)
    def dfs(bounds,F,depth):
        if max_nodes is not None and stats['nodes']>=max_nodes:
            stats['unknown']=True; return None
        stats['nodes']+=1; stats['depth']=max(stats['depth'],depth)
        force_steps=[]
        def wrap(p):
            for ii,fl,cp,Fb in reversed(force_steps):
                p=ForceProof(inst,h,Fb,ii,fl,cp,p)
            return p
        # clause propagation: falsified clauses and unit forcing
        if use_clauses:
            while use_force:
                p=db.find_falsified(F)
                if p is not None:
                    stats['clauses']+=1
                    return wrap(p)
                u=db.find_unit(F,dom)
                if u is None: break
                cp,ii,fl=u
                Fb=frozenset(F)
                force_steps.append((ii,fl,cp,Fb))
                F=F|fl
                bounds=bounds_from_F(lp,F)
                stats['forces']=stats.get('forces',0)+1
        FB={(key[0],key[-1]) for c,key in enumerate(lp.cols) if bounds[c]==(0,0)}
        if set(F)!=FB:
            stats.setdefault('F_mismatch',[]).append((len(F),len(FB),len(set(F)^FB)))
        res=lp.solve(bounds); stats['lp']+=1
        if res.status==2:
            stats['leaf']+=1
            p=leaf_core(inst,h,F,elig,full,stats)
            stats['cert']+=1
            if p is None:
                stats['unknown']=True; return None
            if use_clauses: db.add(p)
            return wrap(p)
        if res.status!=0:
            stats['unknown']=True; return None
        z=res.x
        frac=any(1e-7<z[c]<1-1e-7 and bounds[c]!=(0,0) for c in range(lp.N))
        if not frac:
            got=_integral_schedule(inst,lp,z,elig)
            if got is not None: return ('yes',got[0],got[1])
            sing=_singleton_leaf(inst,h,F,lp,bounds)
            if sing is not None: return ('yes',sing[1],sing[2])
            i=None; L=None; R=None
            for j in range(n):
                times=sorted({key[-1] for c,key in enumerate(lp.cols) if key[0]==j and bounds[c]!=(0,0)})
                if len(times)>1:
                    i=j; mid=times[len(times)//2-1]
                    L=[t for t in times if t>mid]; R=[t for t in times if t<=mid]
                    break
            if i is None:
                stats['unknown']=True; return None
        else:
            i,L,R=None,None,None
            if use_guide and use_clauses:
                g=db.find_guide(F,dom)
                if g is not None:
                    (_,ji,inter,comp),p=g
                    i=ji; R=sorted(inter); L=sorted(comp); stats['guides']+=1
            if i is None:
                i,L,R=choose_frac(lp,z,bounds,inst,q)
            if i is None:
                stats['unknown']=True; return None
        L=set(L); R=set(R)
        FL=F|{(i,t) for t in L}; FR=F|{(i,t) for t in R}
        left=dfs(bounds_from_sets(lp,bounds,i,R),FL,depth+1)
        if isinstance(left,tuple) and left[0]=='yes': return left
        if left is None:
            right=dfs(bounds_from_sets(lp,bounds,i,L),FR,depth+1)
            if isinstance(right,tuple) and right[0]=='yes': return right
            stats['unknown']=True; return None
        if left.core <= F:
            stats['backjumps']+=1
            if use_clauses: db.add(left)
            return wrap(left)
        right=dfs(bounds_from_sets(lp,bounds,i,L),FR,depth+1)
        if isinstance(right,tuple) and right[0]=='yes': return right
        if right is None:
            stats['unknown']=True; return None
        if right.core <= F:
            stats['backjumps']+=1
            if use_clauses: db.add(right)
            return wrap(right)
        p=ComposeProof(inst,h,F,i,L,R,left,right)
        if use_clauses: db.add(p)
        return wrap(p)
    # root
    r=dfs(base,set(),0)
    stats['t']=round(time.time()-t0,4); stats['res_steps']=db.steps
    if r is None:
        return dict(verdict=None,proof=None,schedule=None,machine=None,**stats)
    if isinstance(r,tuple) and r[0]=='yes':
        return dict(verdict=True,proof=None,schedule=r[1],machine=r[2],**stats)
    if db.global_proof is not None:
        r=db.global_proof
    return dict(verdict=False,proof=r,schedule=None,machine=None,**stats)
