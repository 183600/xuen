import sys, time, json, random
sys.path[:0]=['exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
import numpy as np
from sdecc import SDLP
from po import heads_tails
from rdf import check_schedule
from chip import base_corpus, pert_corpus, stress_corpus

def corpora():
    for tag, rows in (('base', base_corpus()), ('pert', pert_corpus()), ('stress', stress_corpus())):
        for row in rows:
            if len(row)==4: name, idx, inst, known = row
            else: idx, known, inst = row; name=tag
            yield tag, name, idx, inst, known

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

def frac_jobs(lp,z):
    s=set()
    for c,key in enumerate(lp.cols):
        if 1e-7 < z[c] < 1-1e-7: s.add(key[0])
    return s

def dca(lp, iters=12, rng=None):
    res=lp.solve()
    if res.status!=0: return res.status,[]
    z=res.x; seen=[]; integrals=[]
    for it in range(iters):
        c = 1.0 - 2.0*z
        # tiny random tie-break to diversify vertices
        if rng is not None:
            c = c + 1e-4*np.array([rng.random() for _ in range(lp.N)])
        r=lp.solve_obj(c)
        if r.status!=0: break
        z2=r.x
        d=decode(lp,z2)
        if d is not None and check_schedule(lp.inst, lp.T, d[0], d[1]):
            integrals.append((it,d))
        key=tuple(sorted((key[0],key[-1]) for cc,key in enumerate(lp.cols) if z2[cc]>1-1e-7))
        seen.append((it,len(frac_jobs(lp,z2)),key))
        if np.max(np.abs(z2-z))<1e-9: break
        z=z2
    return 0, (seen,integrals)
