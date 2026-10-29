"""Prototype: DC-guided fractional-core enumeration for fixed-h SDLP."""
import sys, time, random
sys.path[:0]=['exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
import numpy as np
from scipy.optimize import linprog
from sdecc import SDLP
from po import heads_tails
from rdf import check_schedule
from cert import integer_certificate, verify

def solve_obj(lp, c, bounds):
    return linprog(c, A_ub=lp.A, b_ub=lp.hi, A_eq=lp.A[:lp.n_eq],
                   b_eq=np.ones(lp.n), bounds=bounds, method='highs')

def decode(lp, z):
    n=lp.n
    starts=[None]*n; machs=[None]*n
    for c,key in enumerate(lp.cols):
        if z[c] > 1-1e-7:
            i,t=key[0],key[-1]
            if starts[i] is not None: return None
            starts[i]=t
            if lp.elig_aware: machs[i]=key[1]
    if any(x is None for x in starts): return None
    if not lp.elig_aware:
        busy=[[] for _ in range(lp.m)]
        for i in sorted(range(n), key=lambda i:(starts[i],i)):
            for k in lp.inst['elig'][i]:
                if all(starts[i]+lp.p[i] <= a or starts[i] >= b for a,b in busy[k]):
                    machs[i]=k; busy[k].append((starts[i],starts[i]+lp.p[i])); break
            if machs[i] is None: return None
    return starts,machs

def dca_support(lp, base_bounds, rounds=8):
    res=lp.solve(base_bounds)
    if res.status!=0: return None
    z=res.x; best=None
    for it in range(rounds):
        frac=[c for c in range(lp.N) if 1e-7 < z[c] < 1-1e-7]
        jobs=sorted({lp.cols[c][0] for c in frac})
        if best is None or len(jobs)<len(best[1]):
            best=(z.copy(),jobs)
        if not frac: return z, []
        c=1.0-2.0*z
        r=solve_obj(lp,c,base_bounds)
        if r.status!=0: break
        if np.max(np.abs(r.x-z))<1e-10: break
        z=r.x
    frac=[c for c in range(lp.N) if 1e-7 < z[c] < 1-1e-7]
    jobs=sorted({lp.cols[c][0] for c in frac})
    if best is None or len(jobs)<len(best[1]): best=(z.copy(),jobs)
    return best

def core_decide(inst,h,nodecap=200,corecap=8,elig_aware=None,verbose=False):
    t0=time.time()
    n=inst['n']; m=inst['m']
    if elig_aware is None:
        elig_aware=any(len(set(inst['elig'][i]))<m for i in range(n))
    est,q=heads_tails(inst,0,[0]*n)
    lp=SDLP(inst,h,est,q,use_dom=True,elig_aware=elig_aware)
    stats=dict(nodes=0,leaves=0,lp=0,cert=0,depth=0,unknown=False,core_sizes=[])
    def dom(i):
        return (est[i],h-q[i]-inst['p'][i])
    def bounds_for(fixed):
        b=[]
        for c,key in enumerate(lp.cols):
            i,t=key[0],key[-1]
            if i in fixed and t!=fixed[i]: b.append((0,0))
            else: b.append((0,1))
        return b
    def dfs(fixed,depth,F):
        stats['nodes']+=1; stats['depth']=max(stats['depth'],depth)
        if stats['nodes']>nodecap:
            stats['unknown']=True; return None
        b=bounds_for(fixed)
        stats['lp']+=1
        res=lp.solve(b)
        if res.status==2:
            c=integer_certificate(inst,h,use_dom=True,elig_aware=elig_aware,forbid=F)
            if c is not None and verify(inst,h,c,elig_aware=elig_aware,forbid=F):
                stats['leaves']+=1; stats['cert']+=1
                return ('leaf',c)
            stats['unknown']=True; return None
        if res.status!=0:
            stats['unknown']=True; return None
        d=decode(lp,res.x)
        if d is not None and check_schedule(inst,h,d[0],d[1]):
            return ('yes',d)
        z,jobs=dca_support(lp,b)
        jobs=[i for i in jobs if i not in fixed]
        if not jobs:
            stats['unknown']=True; return None
        stats['core_sizes'].append(len(jobs))
        # choose core subset: all if product small, else single
        doms={i:list(range(dom(i)[0],dom(i)[1]+1)) for i in jobs}
        prod=1
        for i in jobs: prod*=max(1,len(doms[i]))
        C=jobs if prod<=corecap else [max(jobs,key=lambda i:len(doms[i]))]
        C=C[:min(len(C),corecap)]
        # enumerate assignments of C
        combos=[{}]
        for i in C:
            nxt=[]
            for base in combos:
                for t in doms[i]:
                    d2=dict(base); d2[i]=t; nxt.append(d2)
            combos=nxt
            if len(combos)>corecap:
                break
        if len(combos)>corecap:
            C=[C[0]]; combos=[{C[0]:t} for t in doms[C[0]]]
        children=[]
        for asg in combos:
            nf=set(F)
            for i,t in asg.items():
                lo,hi=dom(i)
                for s in range(lo,hi+1):
                    if s!=t: nf.add((i,s))
            # check empty
            if any(all((i,s) in nf for s in range(dom(i)[0],dom(i)[1]+1)) for i in asg):
                continue
            r=dfs({**fixed, **asg},depth+1,nf)
            if r is None: return None
            if r[0]=='yes': return r
            children.append((tuple(sorted(asg.items())),r))
        return ('core',C,children)
    tree=dfs({},0,frozenset())
    stats['t']=round(time.time()-t0,5)
    if tree is None: return dict(verdict=None,**stats)
    if tree[0]=='yes': return dict(verdict=True,schedule=tree[1],**stats)
    return dict(verdict=False,tree=tree,**stats)
