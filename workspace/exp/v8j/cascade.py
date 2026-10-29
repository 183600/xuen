"""CASCADE prototype: certified cover cuts compiled from branch leaves."""
import sys, time
sys.path[:0]=['exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
import numpy as np
from sdecc import SDLP
from po import heads_tails
from cert import integer_certificate, verify, DENS

BIG = tuple(range(1, 400)) + (420, 480, 500, 600, 720, 840, 1000, 1095,
                              1200, 1500, 1800, 2000, 2400, 3000, 3600,
                              4000, 5000, 6000, 7200, 10000, 12000,
                              20000, 50000, 100000)

def _elig(inst):
    return any(len(set(inst['elig'][i])) < inst['m'] for i in range(inst['n']))

def _domain(inst,h,i):
    est,q=heads_tails(inst,0,[0]*inst['n'])
    return est[i], h-q[i]-inst['p'][i]

def allowed(inst,h,i,F):
    lo,hi=_domain(inst,h,i)
    return [t for t in range(lo,hi+1) if (i,t) not in F]

def cert_for(inst,h,F,dens=BIG):
    c=integer_certificate(inst,h,use_dom=True,elig_aware=_elig(inst),forbid=F,dens=dens)
    if c is not None and verify(inst,h,c,forbid=F):
        return c
    return None

def collect(inst,h,nodecap=2000,depthcap=60, max_leaves=1000):
    """DFS collecting NO leaves (F,cert); returns leaves, yes, stats."""
    n,m,p=inst['n'],inst['m'],inst['p']
    est,q=heads_tails(inst,0,[0]*n)
    lp=SDLP(inst,h,est,q,use_dom=True,elig_aware=_elig(inst))
    base=[(0,1)]*lp.N
    stats=dict(nodes=0, lp=0, leaves=0, failed=0, depth=0, t=0)
    leaves=[]; yes=[None]; t0=time.time()
    def solve(bounds):
        stats['nodes']+=1; stats['lp']+=1
        if stats['nodes']>nodecap: return None
        return lp.solve(bounds)
    def allowed_times(i,bounds):
        return sorted({key[-1] for c,key in enumerate(lp.cols)
                       if key[0]==i and bounds[c]!=(0,0)})
    def choose(z,bounds):
        cand=[]
        for i in range(n):
            times=allowed_times(i,bounds)
            if len(times)<=1: continue
            mass=0.0; dist=[]
            for tt in times:
                v=sum(z[c] for c,key in enumerate(lp.cols)
                      if key[0]==i and key[-1]==tt and bounds[c]!=(0,0))
                dist.append((tt,v)); mass+=v
            frac=sum(v for _,v in dist if 1e-7<v<1-1e-7)
            if frac<=1e-7: continue
            cand.append(((mass,q[i],len(inst['succ'][i]),-i),i,dist))
        if not cand: return None,None
        cand.sort(reverse=True)
        _,i,dist=cand[0]
        total=sum(v for _,v in dist); acc=0.0; mid=dist[0][0]
        for tt,v in dist:
            acc+=v
            if acc>=0.5*total: mid=tt; break
        times=[tt for tt,_ in dist]
        if not any(tt>mid for tt in times) or not any(tt<=mid for tt in times):
            mid=times[len(times)//2-1] if len(times)>1 else times[0]
        if not any(tt>mid for tt in times) or not any(tt<=mid for tt in times):
            return None,None
        return i,mid
    def bound_side(bounds,i,mid,side):
        b=list(bounds)
        for c,key in enumerate(lp.cols):
            if key[0]!=i: continue
            tt=key[-1]
            if (side=='lo' and tt>mid) or (side=='hi' and tt<=mid):
                b[c]=(0,0)
        return b
    def integral(z):
        starts=[None]*n; machs=[None]*n
        for c,key in enumerate(lp.cols):
            if z[c]>1-1e-7:
                i,t=key[0],key[-1]
                if starts[i] is not None: return None
                starts[i]=t
                if _elig(inst): machs[i]=key[1]
        if any(x is None for x in starts): return None
        if not _elig(inst):
            busy=[[] for _ in range(m)]
            for i in sorted(range(n),key=lambda i:(starts[i],i)):
                for k in inst['elig'][i]:
                    if all(starts[i]+p[i]<=a or starts[i]>=b for a,b in busy[k]):
                        machs[i]=k; busy[k].append((starts[i],starts[i]+p[i])); break
                if machs[i] is None: return None
        from rdf import check_schedule
        if check_schedule(inst,h,starts,machs): return starts,machs
        return None
    def dfs(bounds,F,depth):
        if depth>depthcap or stats['nodes']>nodecap:
            stats['failed']+=1; return False
        res=solve(bounds)
        if res is None: stats['failed']+=1; return False
        if res.status==2:
            stats['leaves']+=1; stats['depth']=max(stats['depth'],depth)
            c=cert_for(inst,h,F)
            if c is None:
                stats['failed']+=1
                leaves.append((F,None))
                return False
            leaves.append((F,c))
            return False
        if res.status!=0:
            stats['failed']+=1; return False
        z=res.x
        if not any(1e-7<z[c]<1-1e-7 and bounds[c]!=(0,0) for c in range(lp.N)):
            got=integral(z)
            if got is not None:
                yes[0]=got; return True
            stats['failed']+=1; return False
        i,mid=choose(z,bounds)
        if i is None:
            stats['failed']+=1; return False
        times=allowed_times(i,bounds)
        loF=F|{(i,t) for t in times if t>mid}
        hiF=F|{(i,t) for t in times if t<=mid}
        stats['depth']=max(stats['depth'],depth)
        if dfs(bound_side(bounds,i,mid,'lo'),loF,depth+1): return True
        if yes[0] is not None: return True
        if dfs(bound_side(bounds,i,mid,'hi'),hiF,depth+1): return True
        return False
    dfs(base,frozenset(),0)
    stats['t']=round(time.time()-t0,5)
    return leaves,yes[0],stats

def cut_row(lp,F):
    row=np.zeros(lp.N)
    for c,key in enumerate(lp.cols):
        if (key[0],key[-1]) in F:
            row[c]=1.0
    return row

def root_with_cuts(inst,h,leaves,order='size',max_cuts=1000, verbose=False):
    n,m,p=inst['n'],inst['m'],inst['p']
    est,q=heads_tails(inst,0,[0]*n)
    lp=SDLP(inst,h,est,q,use_dom=True,elig_aware=_elig(inst))
    A=lp.A.tocsr().copy(); hi=lp.hi.copy()
    # dedupe cuts, drop trivial (full domain) and keep minimal F
    sets=[]
    for F,c in leaves:
        F=frozenset(F)
        if not F: continue
        # if F contains a full domain of some job, cut is implied by assignment
        trivial=False
        for i in range(n):
            lo,hi_i=_domain(inst,h,i)
            dom={(i,t) for t in range(lo,hi_i+1)}
            if dom and dom<=F:
                trivial=True; break
        if trivial: continue
        sets.append(F)
    sets=list(set(sets))
    if order=='size': sets.sort(key=lambda F:(len(F),sorted(F)))
    elif order=='smallfirst': sets.sort(key=lambda F:(len(F),sorted(F)))
    # subsumption: keep minimal sets
    minimal=[]
    for F in sets:
        if any(G<=F for G in minimal): continue
        minimal=[G for G in minimal if not F<=G]
        minimal.append(F)
    sets=minimal
    used=0; status=None
    for F in sets[:max_cuts]:
        row=cut_row(lp,F)
        if row.sum()==0:
            status=2; used+=1; break
        import scipy.sparse as sp
        A=sp.vstack([A, sp.csr_matrix(-row.reshape(1,-1))]).tocsr()
        hi=np.append(hi, -1.0)
        used+=1
        res=lp_solve_custom(lp,A,hi)
        if verbose: print(' cut',used,'|F|',len(F),'status',res.status)
        if res.status==2:
            status=2; break
        if res.status==0 and ret_integral(res,lp,inst,h) is not None:
            status=0; break
    return dict(used=used,status=status,nsets=len(sets))

def lp_solve_custom(lp,A,hi):
    from scipy.optimize import linprog
    neq=lp.n_eq
    return linprog(np.zeros(A.shape[1]), A_ub=A[neq:], b_ub=hi[neq:],
                   A_eq=A[:neq], b_eq=np.ones(neq), bounds=[(0,1)]*A.shape[1],
                   method='highs')

def ret_integral(res,lp,inst,h):
    n=inst['n']; starts=[None]*n
    for c,key in enumerate(lp.cols):
        if res.x[c]>1-1e-7:
            i,t=key[0],key[-1]
            if starts[i] is not None: return None
            starts[i]=t
    return starts if all(x is not None for x in starts) else None
