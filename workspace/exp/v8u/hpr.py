"""v9.4 HPR-ICF: hole-promoting deterministic specification refinement.

The v9.0 ICF state is a single partial certificate

    (L, U, s, m, pi),   pi : NO(L-1),  Cmax(s) = U,  L <= U.

A fixed-h proof search with depth budget d is not thrown away when it
returns UNKNOWN.  Its partial proof tree is *promoted* to the frontier:
closed leaves keep their NO(h) certificates, and the remaining holes
become open leaves.  Refinement continues only inside the holes.  The
frontier is a specification-refinement tree for the cell (root, h=U-1):

    closed leaf : NO(h | F) proof
    open hole   : cell (F, h) still to be refined
    split       : children exactly partition the parent start domain

The algorithm uses a deterministic canonical order:

  * split job: most fractional job (mass, q, succ, -index);
  * split threshold: median of the LP start-time mass;
  * frontier order: breadth-first, then left-to-right.

With a deterministic LP solver this makes the whole run deterministic.
The final tree is a canonical refinement certificate, not just a trace.

This module implements the live frontier for the weak (large-gap)
corpus.  TAMO/PICF are the baselines: they discard the UNKNOWN search
and split a leaf heuristically; HPR keeps the partial search and all
closed leaves found inside it.
"""
import sys
import time
import math
from collections import deque

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from sdecc import SDLP
from po import heads_tails
from sage import _domain
from cert import verify, integer_certificate
from rdf import check_schedule
from pact import (PACT, pact_decide, _integral_schedule,
                  _singleton_leaf, _elig_aware)
from icf import CertLeafProof, cmax, _proof_forbid
from tamo import (Leaf, Split, collect_leaves, split_leaf, close_empty,
                  allowed_times, box_measure, snapshot, tree_depth,
                  TamoFrontier, TamoPartialCertificate, TamoCertificate,
                  project_forbid)


# --------------------------------------------------------------- local LP
class _LPCache:
    def __init__(self, inst, h):
        self.inst = inst
        self.h = int(h)
        n = inst['n']
        self.elig = _elig_aware(inst)
        self.est, self.q = heads_tails(inst, 0, [0] * n)
        self.lp = SDLP(inst, self.h, self.est, self.q,
                       use_dom=True, elig_aware=self.elig)
        self.bounds_cache = {}
        self.res_cache = {}
        self.solves = 0

    def bounds(self, F):
        key = frozenset(F)
        got = self.bounds_cache.get(key)
        if got is not None:
            return got
        b = [(0, 1)] * self.lp.N
        for c, ck in enumerate(self.lp.cols):
            if (ck[0], ck[-1]) in key:
                b[c] = (0, 0)
        self.bounds_cache[key] = b
        return b

    def solve(self, F):
        key = frozenset(F)
        got = self.res_cache.get(key)
        if got is not None:
            return got, False
        b = self.bounds(key)
        res = self.lp.solve(b)
        self.solves += 1
        self.res_cache[key] = res
        return res, True

    def times(self, i, F):
        b = self.bounds(F)
        return sorted({ck[-1] for c, ck in enumerate(self.lp.cols)
                       if ck[0] == i and b[c] != (0, 0)})

    def dist(self, i, F, z):
        b = self.bounds(F)
        out = []
        for c, ck in enumerate(self.lp.cols):
            if ck[0] == i and b[c] != (0, 0):
                out.append((ck[-1], float(z[c])))
        return out


def _choose_split(cache, F, z, mode='lp'):
    """Canonical split rule.  Returns (i, mid, times) or None."""
    n = cache.inst['n']
    cand = []
    for i in range(n):
        times = cache.times(i, F)
        if len(times) <= 1:
            continue
        if mode == 'domain':
            cand.append((len(times), -i, i, times))
            continue
        dist = cache.dist(i, F, z)
        frac = sum(v for _, v in dist if 1e-7 < v < 1 - 1e-7)
        if frac <= 1e-7:
            continue
        mass = sum(max(0.0, v) for _, v in dist)
        cand.append((frac, mass, cache.q[i], len(cache.inst['succ'][i]),
                     -i, i, times, dist))
    if not cand:
        return None
    if mode == 'domain':
        cand.sort(reverse=True)
        _, _, i, times = cand[0]
        mid = times[max(0, len(times) // 2 - 1)]
        return i, mid, times
    cand.sort(reverse=True)
    _, _, _, _, _, i, times, dist = cand[0]
    total = sum(v for _, v in dist)
    acc = 0.0
    mid = dist[0][0]
    for tt, v in dist:
        acc += v
        if acc >= 0.5 * total:
            mid = tt
            break
    lo = [tt for tt in times if tt <= mid]
    hi = [tt for tt in times if tt > mid]
    if not lo or not hi:
        mid = times[max(0, len(times) // 2 - 1)]
    return i, mid, times


# --------------------------------------------------------------- bounded search
class HStats(dict):
    def __init__(self):
        super().__init__(lp=0, cert_lp=0, nodes=0, holes=0, yes=0,
                         no=0, max_depth=0, cache_hits=0)


def _leaf_or_hole(cache, F, depth, reason):
    return ('hole', frozenset(F), cache.h, reason, int(depth))


def expand(cache, F, depth, budget, stats, mode='lp', memo=None,
           node_budget=None):
    """Bounded proof search for cell (F, cache.h).

    Returns one of
      ('leaf', F, h, CertLeafProof)   closed NO
      ('yes',  F, h, schedule, machine)
      ('hole', F, h, reason, depth)
      ('split', i, mid, F, lo, hi)
    The tree is a partition of F at h; every closed leaf is audited.
    """
    key = (cache.h, frozenset(F), int(budget))
    if memo is not None and key in memo:
        stats['cache_hits'] += 1
        return memo[key]
    if node_budget is not None and stats['nodes'] >= node_budget:
        node = _leaf_or_hole(cache, F, depth, 'node-budget')
        stats['holes'] += 1
        if memo is not None:
            memo[key] = node
        return node
    stats['nodes'] += 1
    stats['max_depth'] = max(stats['max_depth'], depth)
    res, fresh = cache.solve(F)
    if fresh:
        stats['lp'] += 1

    if res.status == 2:
        stats['cert_lp'] += 1
        cert = integer_certificate(cache.inst, cache.h, use_dom=True,
                                   elig_aware=cache.elig, forbid=F)
        if cert is not None and verify(cache.inst, cache.h, cert,
                                       forbid=F):
            node = ('leaf', frozenset(F), cache.h,
                    CertLeafProof(cache.inst, cache.h, F, cert))
            stats['no'] += 1
            if memo is not None:
                memo[key] = node
            return node
        i = _empty_job(cache, F)
        if i is not None:
            node = ('leaf', frozenset(F), cache.h,
                    CertLeafProof(cache.inst, cache.h, F,
                                  {'kind': 'empty', 'job': i}))
            stats['no'] += 1
            if memo is not None:
                memo[key] = node
            return node
        node = _leaf_or_hole(cache, F, depth, 'cert-fail')
        stats['holes'] += 1
        if memo is not None:
            memo[key] = node
        return node
    if res.status != 0:
        node = _leaf_or_hole(cache, F, depth, 'lp-unknown')
        stats['holes'] += 1
        if memo is not None:
            memo[key] = node
        return node

    z = res.x
    frac = False
    b = cache.bounds(F)
    for c, ck in enumerate(cache.lp.cols):
        if b[c] != (0, 0) and 1e-7 < z[c] < 1 - 1e-7:
            frac = True
            break
    if not frac:
        got = _integral_schedule(cache.inst, cache.lp, z, cache.elig)
        if got is None:
            got = _singleton_leaf(cache.inst, cache.h, F, cache.lp, b)
        if got is not None:
            node = ('yes', frozenset(F), cache.h, got[0], got[1])
            stats['yes'] += 1
            if memo is not None:
                memo[key] = node
            return node
        # Integral LP but the decoder failed: fall through to a split.

    if budget <= 0:
        node = _leaf_or_hole(cache, F, depth, 'budget')
        stats['holes'] += 1
        if memo is not None:
            memo[key] = node
        return node

    pick = _choose_split(cache, F, z, mode=mode)
    if pick is None:
        node = _leaf_or_hole(cache, F, depth, 'no-split')
        stats['holes'] += 1
        if memo is not None:
            memo[key] = node
        return node
    i, mid, times = pick
    le = [t for t in times if t <= mid]
    gt = [t for t in times if t > mid]
    if not le or not gt:
        node = _leaf_or_hole(cache, F, depth, 'empty-side')
        stats['holes'] += 1
        if memo is not None:
            memo[key] = node
        return node
    F_lo = frozenset(F) | frozenset((i, t) for t in gt)
    F_hi = frozenset(F) | frozenset((i, t) for t in le)
    lo = expand(cache, F_lo, depth + 1, budget - 1, stats, mode, memo,
                node_budget=node_budget)
    if lo[0] == 'yes':
        if memo is not None:
            memo[key] = lo
        return lo
    hi = expand(cache, F_hi, depth + 1, budget - 1, stats, mode, memo,
                node_budget=node_budget)
    if hi[0] == 'yes':
        if memo is not None:
            memo[key] = hi
        return hi
    node = ('split', i, int(mid), frozenset(F), lo, hi)
    if memo is not None:
        memo[key] = node
    return node


def _empty_job(cache, F):
    for i in range(cache.inst['n']):
        if not cache.times(i, F):
            return i
    return None


# --------------------------------------------------------------- tree graft
def _node_forbid(node):
    return node[1] if node[0] == 'leaf' else node[3]


def _count_holes(node, out):
    tag = node[0]
    if tag in ('hole', 'leaf'):
        if tag == 'hole':
            out.append(node)
        return
    _count_holes(node[4], out)
    _count_holes(node[5], out)


def _to_tamo(node, cache, L0, proof0, H0, parent=None, side=None):
    """Convert an expand() tree to mutable TAMO nodes."""
    tag = node[0]
    if tag == 'leaf':
        _, F, h, proof = node
        lf = Leaf(F, L0, proof, box_measure(cache.inst, H0, F),
                  parent, side)
        lf.closed = True
        lf.h = int(h)
        return lf
    if tag == 'hole':
        _, F, h, reason, depth = node
        lf = Leaf(F, L0, proof0, box_measure(cache.inst, H0, F),
                  parent, side)
        lf.closed = False
        lf.h = None
        return lf
    if tag == 'split':
        _, i, mid, F, lo, hi = node
        sp = Split(F, i, mid)
        sp.lo = _to_tamo(lo, cache, L0, proof0, H0, sp, 'lo')
        sp.hi = _to_tamo(hi, cache, L0, proof0, H0, sp, 'hi')
        return sp
    raise ValueError('cannot graft %r' % (tag,))


def _graft(leaf, sub):
    """Replace ``leaf`` by the mutable subtree ``sub``."""
    p = leaf.parent
    if p is None:
        return sub
    if isinstance(sub, Leaf):
        sub.parent = p
        sub.side = leaf.side
    if leaf.side == 'lo':
        p.lo = sub
    else:
        p.hi = sub
    return None


# --------------------------------------------------------------- audit
def _audit_tree(inst, H, root, L0, proof0):
    fp = TamoFrontier(inst, H, snapshot(root))
    return bool(fp.audit_rdf()), fp


def _tree_hash(node):
    tag = node[0]
    if tag == 'leaf':
        _, F, closed, L, h, proof = node
        return ('leaf', tuple(sorted(F)), bool(closed), int(L), int(h),
                getattr(proof, 'kind', None))
    return ('split', node[1], node[2], tuple(sorted(node[3])),
            _tree_hash(node[4]), _tree_hash(node[5]))


# --------------------------------------------------------------- driver
def run_hpr(inst, known, name, idx, initial=None, budget=1,
            mode='lp', max_steps=200000, audit_every=50,
            collect_tree=False, B0=None, node_budget=None):
    """Run HPR-ICF on one instance.

    ``initial`` = (L, U, schedule, machine, proof) from weak/PACT init.
    ``budget`` is the per-expansion depth budget d.
    """
    t0 = time.time()
    if initial is None:
        from hap import init_weak
        L0, U0, s, m, proof0 = init_weak(inst)
    else:
        L0, U0, s, m, proof0 = initial
    L0, U0 = int(L0), int(U0)
    s, m = list(s), list(m)
    if not check_schedule(inst, cmax(inst, s), s, m):
        return dict(name=name, idx=idx, known=known, ok=False,
                    error='bad-initial-schedule', t=0.0)

    H0 = U0 - 1
    U = U0
    H = U - 1
    Mmax = box_measure(inst, H0, frozenset())
    root = Leaf(frozenset(), L0, proof0, Mmax)
    holder = [root]

    steps = splits = 0
    yes = no = 0
    lp = cert_lp = nodes = holes_made = 0
    max_leaves = 1
    partial_checks = partial_fail = 0
    final_ok = False
    tree_done = False
    limit_hit = False
    stats_total = HStats()

    queue = deque([root])
    caches = {}

    def cache_for(h):
        c = caches.get(h)
        if c is None:
            c = _LPCache(inst, h)
            caches[h] = c
        return c

    def audit_state():
        nonlocal partial_checks, partial_fail
        fp = TamoFrontier(inst, U - 1, snapshot(holder[0]))
        pc = TamoPartialCertificate(inst, U - 1, fp, s, m, probe=steps)
        partial_checks += 1
        if not pc.audit_rdf():
            partial_fail += 1

    audit_state()
    while True:
        # drop stale/closed holes from the front of the queue
        while queue:
            q = queue[0]
            if q.closed or q.L >= U:
                queue.popleft()
                continue
            break
        if not queue:
            break
        if steps >= max_steps:
            limit_hit = True
            break
        leaf = queue.popleft()
        if leaf.closed or leaf.L >= U:
            continue
        H = U - 1
        cache = cache_for(H)
        stats = HStats()
        node = expand(cache, leaf.F, 0, int(budget), stats, mode=mode,
                      node_budget=node_budget)
        steps += 1
        lp += stats['lp']
        cert_lp += stats['cert_lp']
        nodes += stats['nodes']
        holes_made += stats['holes']
        yes += stats['yes']
        no += stats['no']
        for k in ('max_depth', 'cache_hits'):
            stats_total[k] = max(stats_total[k], stats[k])

        if node[0] == 'yes':
            s2, m2 = node[3], node[4]
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U = c2
                H = U - 1
                s, m = list(s2), list(m2)
                # close leaves that are now empty or below the new target
                leaves = []
                collect_leaves(holder[0], leaves)
                for x in leaves:
                    if x.closed:
                        continue
                    if close_empty(inst, x, H):
                        queue = deque(z for z in queue if z is not x)
                    elif x.L >= U:
                        x.closed = True
                        x.h = x.L - 1
                        queue = deque(z for z in queue if z is not x)
            # the expanded leaf stays in the queue; retry at the new H
            if not leaf.closed and leaf.L < U:
                queue.appendleft(leaf)
            audit_state()
            continue

        if node[0] == 'leaf':
            # closed whole cell: replace the leaf by a closed leaf
            leaf.closed = True
            leaf.h = int(node[2])
            leaf.proof = node[3]
            no += 0
        else:
            sub = _to_tamo(node, cache, L0, proof0, H0)
            newroot = _graft(leaf, sub)
            if newroot is not None:
                holder[0] = newroot
            # enqueue the new holes in left-to-right order
            new_holes = []
            _collect_holes_mut(sub, new_holes)
            for x in new_holes:
                if close_empty(inst, x, H) or x.L >= U:
                    continue
                queue.append(x)
            splits += 1

        leaves = []
        collect_leaves(holder[0], leaves)
        max_leaves = max(max_leaves, len(leaves))

        if audit_every and steps % audit_every == 0:
            audit_state()

    # final audit
    leaves = []
    collect_leaves(holder[0], leaves)
    open_count = sum(1 for x in leaves if not x.closed)
    fp = TamoFrontier(inst, U - 1, snapshot(holder[0]))
    cert = TamoCertificate(inst, U - 1, fp, s, m)
    final_ok = bool(cert.audit_rdf()) and open_count == 0
    tree_done = open_count == 0
    partial = TamoPartialCertificate(
        inst, U - 1, TamoFrontier(inst, U - 1, snapshot(holder[0])),
        s, m, probe=steps)
    partial_final = bool(partial.audit_rdf())
    dt = time.time() - t0
    out = dict(
        name=name, idx=idx, known=known, budget=int(budget), mode=mode,
        node_budget=node_budget,
        L0=L0, U0=U0, L=fp.L, U=U, opt=U,
        steps=steps, splits=splits, yes=yes, no=no,
        lp=lp, cert_lp=cert_lp, nodes=nodes, holes=holes_made,
        leaves=len(leaves), open=open_count, max_leaves=max_leaves,
        depth=tree_depth(holder[0]),
        cache_hits=stats_total.get('cache_hits', 0),
        max_depth=stats_total.get('max_depth', 0),
        partial_checks=partial_checks, partial_fail=partial_fail,
        certified=bool(tree_done and fp.L == U and final_ok),
        audit=final_ok, proof=final_ok,
        partial_final=partial_final,
        cert_h=(U - 1 if tree_done else None),
        limit_hit=limit_hit,
        t=round(dt, 4),
        ok=bool(tree_done and U == known and final_ok and
                partial_fail == 0),
    )
    if collect_tree:
        out['tree'] = snapshot(holder[0])
        out['tree_hash'] = _tree_hash(snapshot(holder[0]))
        out['schedule'] = s
        out['machine'] = m
    return out


def _collect_holes_mut(node, out):
    if isinstance(node, Leaf):
        if not node.closed:
            out.append(node)
        return
    _collect_holes_mut(node.lo, out)
    _collect_holes_mut(node.hi, out)
