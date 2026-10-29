"""Prototype best-first fixed-h frontier with auditable BranchProof leaves."""
import sys, time, heapq, math
sys.path[:0] = ['exp/v10','exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from sdecc import SDLP
from cert import integer_certificate, verify
from sage import BranchProof, _domain, _elig_aware
from pact import _integral_schedule, _singleton_leaf
from po import heads_tails
from rdf import check_schedule


def cmax(inst, s):
    return max(s[i] + inst['p'][i] for i in range(inst['n']))


class Node:
    __slots__ = ('F','depth','lp','res','status','cert','split','ch','z','mass','parent','_frac','schedule','machine')
    def __init__(self, F, depth, parent=None):
        self.F = frozenset(F); self.depth = depth; self.parent = parent
        self.lp = None; self.res = None; self.status = 'new'
        self.cert = None; self.split = None; self.ch = None
        self.z = None; self.mass = 0.0


def _frac_stats(lp, z):
    n = lp.n
    dists = {}
    for c, key in enumerate(lp.cols):
        i, t = key[0], key[-1]
        d = dists.setdefault(i, {})
        d[t] = d.get(t, 0.0) + float(z[c])
    out = {}
    for i, d in dists.items():
        times = sorted(d)
        if len(times) <= 1:
            continue
        frac = sum(v for v in d.values() if 1e-7 < v < 1-1e-7)
        if frac <= 1e-7:
            continue
        mass = sum(d.values())
        peak = max(d.values())
        ent = -sum(v*math.log(v) for v in d.values() if v > 1e-12)
        mean = sum(t*v for t,v in d.items())/max(mass,1e-12)
        var = sum(v*(t-mean)**2 for t,v in d.items())/max(mass,1e-12)
        out[i] = dict(times=times, dist=d, frac=frac, mass=mass,
                      peak=peak, entropy=ent, spread=math.sqrt(var))
    return out


def choose_default(inst, h, stats, z, lp):
    # PACT-like: (mass, q, succ, -i)
    n = inst['n']
    est, q = heads_tails(inst, 0, [0]*n)
    cand = []
    for i, d in stats.items():
        cand.append(((d['mass'], q[i], len(inst['succ'][i]), -i), i, d))
    if not cand:
        return None
    cand.sort(reverse=True)
    _, i, d = cand[0]
    total = d['mass']
    acc = 0.0; mid = d['times'][0]
    for t in d['times']:
        acc += d['dist'][t]
        if acc >= 0.5*total:
            mid = t; break
    lo = [t for t in d['times'] if t > mid]
    hi = [t for t in d['times'] if t <= mid]
    if not lo or not hi:
        mid = d['times'][len(d['times'])//2 - 1]
        lo = [t for t in d['times'] if t > mid]
        hi = [t for t in d['times'] if t <= mid]
    if not lo or not hi:
        return None
    return i, mid


def solve_node(inst, h, node, est, q, elig, stats):
    node.lp = SDLP(inst, h, est, q, use_dom=True, elig_aware=elig, forbid=node.F)
    base = [(0,1)]*node.lp.N
    stats['lp'] += 1
    node.res = node.lp.solve(base)
    if node.res.status == 2:
        stats['cert_lp'] += 1
        cert = integer_certificate(inst, h, use_dom=True, elig_aware=elig, forbid=node.F)
        if cert is not None and verify(inst, h, cert, forbid=node.F):
            node.status = 'no'; node.cert = cert; return
        # empty domain leaf
        for i in range(inst['n']):
            lo, hi = _domain(inst, h, i)
            if lo <= hi and all((i,t) in node.F for t in range(lo,hi+1)):
                node.status = 'no'; node.cert = {'kind':'empty','job':i}; return
        node.status = 'unknown'; return
    if node.res.status != 0:
        node.status = 'unknown'; return
    z = node.res.x
    stats['nodes'] += 1
    frac = _frac_stats(node.lp, z)
    if not frac:
        got = _integral_schedule(inst, node.lp, z, elig)
        if got is None:
            got = _singleton_leaf(inst, h, node.F, node.lp, base)
        if got is not None:
            node.status = 'yes'
            node.schedule, node.machine = got
            return
        # integral but ambiguous: split any job with >1 allowed time
        times_all = {}
        for c,key in enumerate(node.lp.cols):
            times_all.setdefault(key[0], set()).add(key[-1])
        for i in range(inst['n']):
            ts = sorted(times_all.get(i, ()))
            if len(ts) > 1:
                frac[i] = dict(times=ts, dist={t:0.0 for t in ts},
                               frac=0.0, mass=0.0, peak=0.0,
                               entropy=0.0, spread=0.0)
                break
        if not frac:
            node.status = 'unknown'; return
    node.z = z
    node.status = 'open'
    node.mass = sum(d['mass'] for d in frac.values())
    node._frac = frac
    stats['frac_nodes'] += 1


def build_tree(node):
    if node.status == 'no':
        if node.cert.get('kind') == 'empty':
            return ('empty', frozenset(node.F), node.cert['job'])
        return ('leaf', frozenset(node.F), node.cert)
    i, mid = node.split
    return ('node', i, mid, frozenset(node.F), build_tree(node.ch[0]), build_tree(node.ch[1]))


def frontier_decide(inst, h, budget=1000, order='mass', policy=None):
    t0=time.time()
    n,m,p=inst['n'],inst['m'],inst['p']
    elig=_elig_aware(inst)
    est,q=heads_tails(inst,0,[0]*n)
    stats=dict(lp=0,cert_lp=0,nodes=0,frac_nodes=0,splits=0,t=0.0)
    root=Node(frozenset(),0)
    solve_node(inst,h,root,est,q,elig,stats)
    if root.status=='no':
        tree=build_tree(root); proof=BranchProof(inst,h,tree,stats)
        stats['t']=round(time.time()-t0,5)
        return dict(verdict=False,proof=proof,schedule=None,machine=None,**stats)
    if root.status=='yes':
        stats['t']=round(time.time()-t0,5)
        return dict(verdict=True,proof=None,schedule=root.schedule,machine=root.machine,**stats)
    if root.status=='unknown':
        stats['t']=round(time.time()-t0,5)
        return dict(verdict=None,proof=None,schedule=None,machine=None,**stats)
    # open frontier; heap key negative mass (higher mass first)
    heap=[]
    counter=0
    def push(node):
        nonlocal counter
        counter+=1
        key = -node.mass if order=='mass' else node.depth
        heapq.heappush(heap,(key,counter,node))
    push(root)
    open_count=1
    while heap and stats['lp']<budget:
        _,_,node=heapq.heappop(heap)
        # choose split
        ch=choose_default(inst,h,node._frac,node.z,node.lp)
        if ch is None:
            node.status='unknown'; open_count-=1; continue
        i,mid=ch
        times=sorted(node._frac[i]['times'])
        loF=node.F | {(i,t) for t in times if t>mid}
        hiF=node.F | {(i,t) for t in times if t<=mid}
        a=Node(loF,node.depth+1,node); b=Node(hiF,node.depth+1,node)
        node.ch=(a,b); node.split=(i,mid); node.status='split'; stats['splits']+=1
        # solve children lazily? solve now for mass priority
        solve_node(inst,h,a,est,q,elig,stats)
        solve_node(inst,h,b,est,q,elig,stats)
        for child in (a,b):
            if child.status=='yes':
                stats['t']=round(time.time()-t0,5)
                return dict(verdict=True,proof=None,schedule=child.schedule,machine=child.machine,**stats)
            if child.status=='no':
                open_count-=1
            elif child.status=='open':
                push(child)
            else:
                open_count-=1  # unknown treated as not closable; will fail later
        # node was already popped; open_count accounting: parent open replaced by children
        # parent contributed 1; children: closed -> 0, open -> +1
        # we decremented for closed/unknown; for open we pushed but need count
        # fix: open_count currently parent removed? We didn't decrement on pop.
        # Let's recompute from scratch to avoid bugs.
        open_count = sum(1 for x in [root] if x.status=='open')
        # simpler: count all open nodes by traversal
        def count_open(x):
            if x.status=='open': return 1
            if x.status=='split': return count_open(x.ch[0])+count_open(x.ch[1])
            return 0
        open_count=count_open(root)
        if open_count==0:
            # all leaves closed no? If any unknown, fail
            def any_unknown(x):
                if x.status in ('unknown','new'): return True
                if x.status=='split': return any_unknown(x.ch[0]) or any_unknown(x.ch[1])
                return False
            if any_unknown(root):
                stats['t']=round(time.time()-t0,5)
                return dict(verdict=None,proof=None,schedule=None,machine=None,**stats)
            tree=build_tree(root)
            proof=BranchProof(inst,h,tree,stats)
            if not proof.audit_rdf():
                stats['t']=round(time.time()-t0,5)
                return dict(verdict=None,proof=None,schedule=None,machine=None,audit=False,**stats)
            stats['t']=round(time.time()-t0,5)
            return dict(verdict=False,proof=proof,schedule=None,machine=None,**stats)
    stats['t']=round(time.time()-t0,5)
    return dict(verdict=None,proof=None,schedule=None,machine=None,budget_hit=True,**stats)
