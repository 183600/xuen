"""v10.0 MHT: Monotone Horizon Tree with a bounded certificate cache.

MHT keeps the v9.0 ICF invariant

    L <= OPT <= U,   pi : NO(L-1),   Cmax(s)=U,

but makes the frontier live and gives every internal proof node the
monotone horizon

    h(parent) = min(h(left), h(right)).

Thus a node may be closed at a low horizon while its sibling is still
being lifted; the parent's horizon rises exactly when both children do.
A frontier leaf can be probed at its own lower bound L_f, a feasible
fractional LP splits it, and a NO Farkas certificate lifts its horizon
by one.  When the number of frontier leaves exceeds W, two sibling
leaves are merged into a parent whose proof is the min-horizon join;
the retired children are put into a bounded cache.  If the parent has to
be opened again, cached children are restored before any LP is solved.

The cache is the round's "cache replacement" object: keys are child
boxes, entries are certified subtrees, and an eviction only loses work,
never soundness.  MHT reports miss/hit/eviction counts and the certificate
communication (number of messages that had to be recomputed).
"""
import sys
import time
import math
import collections

sys.path[:0] = ['exp/v10e', 'exp/v10b', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof
from cert import integer_certificate, verify
from chip import base_bounds  # noqa: F401  (kept for compatibility)
from icf import FrontierProof, cmax
from pact import (_integral_schedule, _elig_aware, PACT, pact_decide)
from po import heads_tails
from rdf import check_schedule
from sage import _domain
from sdecc import SDLP


# --------------------------------------------------------------- boxes
def root_box(inst, h):
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    lo = [int(est[i]) for i in range(n)]
    hi = [int(h - q[i] - inst['p'][i]) for i in range(n)]
    return lo, hi


def forbid_box(inst, h, lo, hi):
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    F = set()
    for i in range(n):
        a = est[i]
        b = h - q[i] - inst['p'][i]
        for t in range(a, b + 1):
            if t < lo[i] or t > hi[i]:
                F.add((i, t))
    return frozenset(F)


def effective(inst, h, lo, hi):
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    a = [max(int(lo[i]), int(est[i])) for i in range(n)]
    b = [min(int(hi[i]), int(h - q[i] - inst['p'][i])) for i in range(n)]
    if any(a[i] > b[i] for i in range(n)):
        return None
    return a, b


# ------------------------------------------------------- merged proofs
class MergedProof(Proof):
    """The join of two child proofs at the smaller child horizon.

    left  proves NO(hL | FL), right proves NO(hR | FR), and the two
    boxes partition the parent box F.  The join proves
    NO(min(hL,hR) | F).
    """

    kind = 'mht-join'

    def __init__(self, inst, h, F, i, mid, left, right):
        super().__init__(inst, h)
        self.forbid0 = frozenset(F)
        self.i = int(i)
        self.mid = int(mid)
        self.left = left
        self.right = right

    def _allowed(self, i, F):
        lo, hi = _domain(self.inst, self.h, i)
        return [t for t in range(lo, hi + 1) if (i, t) not in F]

    def audit_rdf(self):
        try:
            if self.left is None or self.right is None:
                return False
            if self.left.h < self.h or self.right.h < self.h:
                return False
            if not self.left.audit_rdf() or not self.right.audit_rdf():
                return False
            times = sorted(self._allowed(self.i, self.forbid0))
            lo_t = [t for t in times if t > self.mid]
            hi_t = [t for t in times if t <= self.mid]
            if not lo_t or not hi_t:
                return False
            FL = self.forbid0 | {(self.i, t) for t in lo_t}
            FR = self.forbid0 | {(self.i, t) for t in hi_t}
            if not set(_proof_forbid(self.left)) <= set(FL):
                return False
            if not set(_proof_forbid(self.right)) <= set(FR):
                return False
            return True
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


def _proof_forbid(p):
    seen = set()
    while p is not None and id(p) not in seen:
        seen.add(id(p))
        f = getattr(p, 'forbid0', None)
        if f is not None:
            return frozenset(f)
        p = getattr(p, 'source', None)
    return frozenset()


class EmptyProof(Proof):
    kind = 'mht-empty'

    def __init__(self, inst, h, F, job):
        super().__init__(inst, h)
        self.forbid0 = frozenset(F)
        self.job = int(job)

    def audit_rdf(self):
        try:
            lo, hi = _domain(self.inst, self.h, self.job)
            return all((self.job, t) in self.forbid0
                       for t in range(lo, hi + 1))
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


class FarkasLeaf(Proof):
    kind = 'mht-farkas'

    def __init__(self, inst, h, F, cert):
        super().__init__(inst, h)
        self.forbid0 = frozenset(F)
        self.cert = cert

    def audit_rdf(self):
        try:
            return bool(self.cert is not None and
                        verify(self.inst, self.h, self.cert,
                               forbid=self.forbid0))
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


# ------------------------------------------------------------ cache
class LeafCache:
    """Bounded cache of retired certified children.

    Entry: key -> dict(L, proof, lo, hi, split, stamp, uses, value).
    Replacement policies are LRU, LFU and value (progress x width).
    Belady is evaluated offline from a request trace, see bench_mht.py.
    """

    def __init__(self, capacity, policy='lru'):
        self.capacity = int(capacity) if capacity is not None else None
        self.policy = policy
        self.data = {}
        self.clock = 0
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.restores = 0
        self.partial = 0
        self.trace = []

    def __len__(self):
        return len(self.data)

    def _touch(self, key, ent):
        self.clock += 1
        ent['stamp'] = self.clock
        ent['uses'] = ent.get('uses', 0) + 1

    def get(self, key):
        ent = self.data.get(key)
        if ent is None:
            self.misses += 1
            self.trace.append(('miss', key))
            return None
        self._touch(key, ent)
        self.hits += 1
        self.trace.append(('hit', key))
        return ent

    def put(self, key, ent):
        if self.capacity is not None and self.capacity <= 0:
            self.evictions += 1
            return
        self.clock += 1
        ent['stamp'] = self.clock
        ent['uses'] = ent.get('uses', 0) + 1
        self.data[key] = ent
        if self.capacity is not None:
            while len(self.data) > self.capacity:
                self._evict()

    def _evict(self):
        if not self.data:
            return
        if self.policy == 'lru':
            k = min(self.data, key=lambda x: self.data[x]['stamp'])
        elif self.policy == 'lfu':
            k = min(self.data, key=lambda x: (self.data[x]['uses'],
                                              self.data[x]['stamp']))
        elif self.policy == 'value':
            k = min(self.data, key=lambda x: (self.data[x].get('value', 0),
                                              self.data[x]['stamp']))
        elif self.policy == 'fifo':
            k = min(self.data, key=lambda x: self.data[x].get('born', 0))
        else:
            k = min(self.data, key=lambda x: self.data[x]['stamp'])
        del self.data[k]
        self.evictions += 1

    def clear(self):
        self.data.clear()
        self.trace.clear()


# ------------------------------------------------------------ node
class Node:
    __slots__ = ('lo', 'hi', 'L', 'proof', 'parent', 'children', 'split',
                 'depth', 'created', 'dead')

    def __init__(self, lo, hi, L, proof, parent=None, depth=0, created=0):
        self.lo = tuple(int(x) for x in lo)
        self.hi = tuple(int(x) for x in hi)
        self.L = int(L)
        self.proof = proof
        self.parent = parent
        self.children = None
        self.split = None
        self.depth = int(depth)
        self.created = int(created)
        self.dead = False

    def key(self):
        return (self.lo, self.hi)

    def h(self):
        if self.proof is not None:
            return int(self.proof.h)
        return int(self.L) - 1


class MHT:
    def __init__(self, inst, W=32, cache_cap=64, evict='lru',
                 policy='lower', max_probes=20000, max_splits=20000,
                 max_contract=20000, max_time=None, use_aco=False,
                 split_mode='mass', verbose=False):
        self.inst = inst
        self.W = int(W)
        self.policy = policy
        self.max_probes = int(max_probes)
        self.max_splits = int(max_splits)
        self.max_contract = int(max_contract)
        self.max_time = max_time
        self.use_aco = bool(use_aco)
        self.split_mode = split_mode
        self.verbose = verbose
        self.cache = LeafCache(cache_cap, evict)
        self.stats = dict(probes=0, lp=0, cert_lp=0, pin_lp=0, nodes=0,
                          splits=0, contracts=0, restores=0, memory_stops=0,
                          unknown=0, dead=0, peak_leaves=1, max_depth=0,
                          cache_hits=0, cache_misses=0, cache_evict=0,
                          cache_restores=0, cache_partial=0,
                          recomputed_children=0, mesg=0)
        self.t0 = time.time()
        self.root = None
        self.L = 0
        self.U = 0

    # ---- tree helpers
    def _leaves(self):
        out = []
        stack = [self.root] if self.root is not None else []
        while stack:
            nd = stack.pop()
            if nd.dead:
                continue
            if nd.children is None:
                out.append(nd)
            else:
                stack.append(nd.children[1])
                stack.append(nd.children[0])
        return out

    def _open(self):
        return [f for f in self._leaves() if f.L < self.U and not f.dead]

    def _global_L(self):
        best = self.U
        for f in self._leaves():
            if f.L < best:
                best = f.L
        return int(best)

    def _refresh_dead(self):
        H = self.U - 1
        n = self.inst['n']
        for f in self._leaves():
            eff = effective(self.inst, H, f.lo, f.hi)
            if eff is None:
                if not f.dead:
                    f.dead = True
                    self.stats['dead'] += 1
                continue
            # empty effective box at target H is an immediate NO(H) leaf
            F = forbid_box(self.inst, H, *eff)
            empty = None
            for i in range(n):
                lo, hi = _domain(self.inst, H, i)
                aa, bb = max(lo, eff[0][i]), min(hi, eff[1][i])
                if aa > bb or all((i, t) in F for t in range(aa, bb + 1)):
                    empty = i
                    break
            if empty is not None and f.proof is not None and f.proof.h < H:
                f.proof = EmptyProof(self.inst, H, F, empty)
                f.L = H + 1

    # ---- probe
    def _probe(self, f):
        h = f.L
        eff = effective(self.inst, h, f.lo, f.hi)
        if eff is None:
            F = forbid_box(self.inst, h, f.lo, f.hi)
            job = 0
            for j in range(self.inst['n']):
                ej, qj = heads_tails(self.inst, 0, [0] * self.inst['n'])
                lo_j = max(ej[j], f.lo[j])
                hi_j = min(h - qj[j] - self.inst['p'][j], f.hi[j])
                if lo_j > hi_j:
                    job = j
                    break
            pr = EmptyProof(self.inst, h, F, job)
            self.stats['empty'] = self.stats.get('empty', 0) + 1
            return 'no', (h + 1, pr)
        a, b = eff
        F = forbid_box(self.inst, h, a, b)
        n = self.inst['n']
        est, q = heads_tails(self.inst, 0, [0] * n)
        elig = _elig_aware(self.inst)
        try:
            lp = SDLP(self.inst, h, est, q, use_dom=True,
                      elig_aware=elig, forbid=F)
            self.stats['lp'] += 1
            res = lp.solve() if lp.N else None
        except Exception:
            return 'split', (None, None, a, b)
        self.stats['nodes'] += 1
        if lp.N == 0 or res is None:
            self.stats['cert_lp'] += 1
            cert = integer_certificate(self.inst, h, use_dom=True,
                                       elig_aware=elig, forbid=F)
            if cert is not None and verify(self.inst, h, cert, forbid=F):
                return 'no', (h + 1, FarkasLeaf(self.inst, h, F, cert))
            return 'split', (None, None, a, b)
        if res.status == 2:
            self.stats['cert_lp'] += 1
            cert = integer_certificate(self.inst, h, use_dom=True,
                                       elig_aware=elig, forbid=F)
            if cert is not None and verify(self.inst, h, cert, forbid=F):
                return 'no', (h + 1, FarkasLeaf(self.inst, h, F, cert))
            # verified fallback: a complete NO proof for this box
            r = pact_decide(self.inst, h, depthcap=None, nodecap=None,
                            forbid0=F)
            self.stats['fallback'] = self.stats.get('fallback', 0) + 1
            if r['verdict'] is False:
                return 'no', (h + 1, r['proof'])
            if r['verdict'] is True:
                return 'yes', (r['schedule'], r['machine'])
            return 'split', (None, None, a, b)
        if res.status == 0:
            got = _integral_schedule(self.inst, lp, res.x, elig)
            if got is not None:
                return 'yes', got
            return 'split', (lp, res.x, a, b)
        return 'split', (None, None, a, b)

    def _choose_split(self, lp, z, a, b):
        inst = self.inst
        n = inst['n']
        q = getattr(lp, 'q', [0] * n)
        cand = []
        for i in range(n):
            times = list(range(a[i], b[i] + 1))
            if len(times) <= 1:
                continue
            mass = 0.0
            frac = 0.0
            dist = []
            for t in times:
                v = 0.0
                for c, key in enumerate(lp.cols):
                    if key[0] == i and key[-1] == t:
                        v += float(z[c])
                if v > 1e-12:
                    dist.append((t, v))
                    mass += v
                    if 1e-7 < v < 1 - 1e-7:
                        frac += v
            if len(dist) <= 1 or mass <= 1e-12:
                continue
            total = sum(v for _, v in dist)
            acc = 0.0
            mid = dist[0][0]
            for t, v in dist:
                acc += v
                if acc >= 0.5 * total:
                    mid = t
                    break
            ts = [t for t, _ in dist]
            if not any(t > mid for t in ts) or not any(t <= mid for t in ts):
                mid = ts[len(ts) // 2 - 1]
            if not any(t > mid for t in ts) or not any(t <= mid for t in ts):
                continue
            cand.append((i, dist, mass, frac))
        if not cand:
            i = max(range(n), key=lambda j: (b[j] - a[j], q[j], -j))
            if b[i] <= a[i]:
                return None, None
            mid = (a[i] + b[i]) // 2
            return i, mid
        def score(c):
            i, dist, mass, frac = c
            return (frac, mass, q[i], len(dist), -i)
        cand.sort(key=score, reverse=True)
        i, dist, mass, frac = cand[0]
        total = sum(v for _, v in dist)
        acc = 0.0
        mid = dist[0][0]
        for t, v in dist:
            acc += v
            if acc >= 0.5 * total:
                mid = t
                break
        ts = [t for t, _ in dist]
        if not any(t > mid for t in ts) or not any(t <= mid for t in ts):
            mid = ts[len(ts) // 2 - 1]
        if not any(t > mid for t in ts) or not any(t <= mid for t in ts):
            return None, None
        return i, mid

    def _child_boxes(self, f, i, mid):
        a, b = f.lo, f.hi
        lo1 = list(a); hi1 = list(b); hi1[i] = mid
        lo2 = list(a); hi2 = list(b); lo2[i] = mid + 1
        return (tuple(lo1), tuple(hi1)), (tuple(lo2), tuple(hi2))

    def _make_child(self, parent, lo, hi):
        return Node(lo, hi, parent.L, parent.proof, parent=parent,
                    depth=parent.depth + 1,
                    created=self.stats['splits'] + self.stats['contracts'])

    def _split(self, f, lp, z, a, b):
        # Children partition the parent box at the *target* horizon U-1,
        # not the probe horizon; otherwise the final certificate misses
        # schedules that only become domain-feasible at U-1.
        i, mid = None, None
        # If this node was contracted, prefer the original split so that
        # cached children are exact keys (a cache hit, not a re-probe).
        if f.children is None and f.split is not None:
            oi, omid = f.split
            boxes0 = self._child_boxes(f, oi, omid)
            if boxes0 is not None and a[oi] <= omid < b[oi]:
                if (self.cache.data.get(boxes0[0]) is not None or
                        self.cache.data.get(boxes0[1]) is not None):
                    i, mid = oi, omid
        if i is None and lp is not None:
            i, mid = self._choose_split(lp, z, a, b)
        H = self.U - 1
        effH = effective(self.inst, H, f.lo, f.hi)
        if effH is not None:
            aH, bH = effH
            if i is not None and not (aH[i] <= mid < bH[i]):
                i, mid = None, None
        if i is None or not (a[i] <= mid < b[i]):
            i = max((j for j in range(self.inst['n'])
                     if b[j] > a[j]),
                    key=lambda j: (b[j] - a[j], -j), default=None)
            if i is None:
                return False
            mid = (a[i] + b[i]) // 2
        boxes = self._child_boxes(f, i, mid)
        f.split = (i, mid)
        f.children = (self._make_child(f, *boxes[0]),
                      self._make_child(f, *boxes[1]))
        self.stats['splits'] += 1
        self.stats['max_depth'] = max(self.stats['max_depth'],
                                      f.children[0].depth)
        # cache restore: exact child boxes
        for ch in f.children:
            ent = self.cache.get(ch.key())
            if ent is not None and ent['proof'] is not None:
                if ent['L'] >= f.L and ent['proof'].h >= f.L - 1:
                    ch.L = ent['L']
                    ch.proof = ent['proof']
                    ch.split = ent.get('split')
                    self.stats['cache_restores'] += 1
                    self.stats['restores'] += 1
                else:
                    self.stats['cache_partial'] += 1
            else:
                self.stats['recomputed_children'] += 1
        return True

    # ---- contraction / cache
    def _contract_one(self):
        leaves = self._leaves()
        groups = {}
        for f in leaves:
            if f.parent is not None:
                groups.setdefault(id(f.parent), []).append(f)
        best = None
        for pid, fs in groups.items():
            if len(fs) != 2:
                continue
            par = fs[0].parent
            if par.dead or par.children is None:
                continue
            if par.L < self._global_L():
                continue
            c0, c1 = fs
            if c0.proof is None or c1.proof is None:
                continue
            h = min(c0.proof.h, c1.proof.h)
            key = (h, par.depth, -par.created)
            if best is None or key > best[0]:
                best = (key, par, c0, c1)
        if best is None:
            return False
        _, par, c0, c1 = best
        h = min(c0.proof.h, c1.proof.h)
        F = forbid_box(self.inst, self.U - 1, par.lo, par.hi)
        i, mid = par.split
        merged = MergedProof(self.inst, h, F, i, mid, c0.proof, c1.proof)
        if not merged.audit_rdf():
            return False
        # cache the retired children
        for ch in (c0, c1):
            ent = dict(L=ch.L, proof=ch.proof, lo=ch.lo, hi=ch.hi,
                       split=ch.split, born=self.cache.clock,
                       value=(ch.L - par.L) * max(1, ch.hi[0] - ch.lo[0] + 1))
            self.cache.put(ch.key(), ent)
        par.children = None
        par.proof = merged
        par.L = h + 1
        # parent keeps par.split for a potential re-open
        self.stats['contracts'] += 1
        self.stats['cache_hits'] = self.cache.hits
        self.stats['cache_misses'] = self.cache.misses
        self.stats['cache_evict'] = self.cache.evictions
        return True

    def _try_restore(self, par):
        """Re-open a contracted parent from the cache, if possible."""
        if par.split is None:
            return False
        i, mid = par.split
        boxes = self._child_boxes(par, i, mid)
        ents = [self.cache.get(b) for b in boxes]
        got = 0
        for ch, ent in zip((None, None), ents):
            pass
        c0 = Node(boxes[0][0], boxes[0][1], par.L, par.proof,
                  parent=par, depth=par.depth + 1,
                  created=self.stats['splits'] + self.stats['contracts'])
        c1 = Node(boxes[1][0], boxes[1][1], par.L, par.proof,
                  parent=par, depth=par.depth + 1,
                  created=self.stats['splits'] + self.stats['contracts'])
        for ch, ent in ((c0, ents[0]), (c1, ents[1])):
            if ent is not None and ent['proof'] is not None \
                    and ent['L'] >= par.L \
                    and ent['proof'].h >= par.L - 1:
                ch.L = ent['L']
                ch.proof = ent['proof']
                ch.split = ent.get('split')
                got += 1
        par.children = (c0, c1)
        par.proof = par.proof if par.proof is not None else c0.proof
        self.stats['restores'] += 1
        self.stats['cache_restores'] += got
        self.stats['recomputed_children'] += 2 - got
        return True

    # ---- final proof
    def _build(self, nd, target):
        H = target
        eff = effective(self.inst, H, nd.lo, nd.hi)
        if eff is None:
            return None
        a, b = eff
        F = forbid_box(self.inst, H, a, b)
        if nd.children is None:
            if nd.proof is None or nd.proof.h < H:
                return None
            return ('leaf', F, nd.proof.h, nd.proof)
        l = self._build(nd.children[0], H)
        r = self._build(nd.children[1], H)
        if l is None or r is None:
            return None
        i, mid = nd.split
        return ('split', i, mid, F, l, r)

    def frontier(self, target):
        tree = self._build(self.root, target)
        if tree is None:
            return None
        return FrontierProof(self.inst, target, tree)

    # ---- main loop
    def run(self):
        inst = self.inst
        co = PACT(inst, pact_mode='complete', use_ga=False)
        lb, ub, sched, mach = co.initial_bounds()
        self.stats['pin_lp'] = int(getattr(co, 'pin_lp', 0))
        if ub is None or sched is None:
            return dict(ok=False, error='no-initial-ub',
                        t=round(time.time() - self.t0, 4))
        L, U = int(lb), int(ub)
        proof = co._ensure_lb_proof(L)
        if proof is None:
            r = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
            if r['verdict'] is False:
                proof = r['proof']
        if proof is None:
            return dict(ok=False, error='no-lb-proof',
                        t=round(time.time() - self.t0, 4))
        init_L, init_U = L, U
        init_sched, init_mach = list(sched), list(mach)
        self.L, self.U = L, U
        H = U - 1
        lo, hi = root_box(inst, H)
        self.root = Node(lo, hi, L, proof)
        self._refresh_dead()
        best_U, best_sched, best_mach = U, list(sched), list(mach)
        probes = 0
        while True:
            if self.max_time is not None and time.time() - self.t0 > self.max_time:
                break
            self._refresh_dead()
            L = self._global_L()
            self.L = L
            if L >= U:
                L = U
                self.L = L
                break
            openf = self._open()
            if not openf:
                L = self._global_L()
                self.L = L
                if L >= U:
                    L = U
                break
            if probes >= self.max_probes or \
                    self.stats['splits'] >= self.max_splits:
                break
            f = min(openf, key=lambda x: (x.L, -x.depth, -x.created))
            status, payload = self._probe(f)
            probes += 1
            self.stats['probes'] += 1
            if status == 'no':
                h, pr = payload
                f.L = h
                f.proof = pr
                self.stats['mesg'] += len(_proof_forbid(pr))
                continue
            if status == 'yes':
                s2, m2 = payload
                c2 = cmax(inst, s2)
                if c2 < U and check_schedule(inst, c2, s2, m2):
                    U, sched, mach = c2, list(s2), list(m2)
                    self.U = U
                    best_U, best_sched, best_mach = U, list(s2), list(m2)
                continue
            if status == 'split':
                lp, z, a, b = payload
                before = len(self._open())
                if before >= self.W:
                    made = False
                    while len(self._open()) >= self.W and \
                            self.stats['contracts'] < self.max_contract:
                        if not self._contract_one():
                            break
                        made = True
                    if len(self._open()) >= self.W and not made:
                        self.stats['memory_stops'] += 1
                        break
                if lp is None:
                    ok = self._split(f, None, None, a, b)
                else:
                    ok = self._split(f, lp, z, a, b)
                if not ok:
                    self.stats['unknown'] += 1
                    break
                while len(self._open()) > self.W and \
                        self.stats['contracts'] < self.max_contract:
                    if not self._contract_one():
                        break
                if len(self._open()) > self.W:
                    self.stats['memory_stops'] += 1
                    break
                peak = len(self._leaves())
                if peak > self.stats['peak_leaves']:
                    self.stats['peak_leaves'] = peak
                continue
            self.stats['unknown'] += 1
            break

        self._refresh_dead()
        L = self._global_L()
        self.L = L
        if L >= U:
            L = U
            self.L = L
        # final or partial certificate
        target = L - 1
        frontier = self.frontier(target)
        final_ok = False
        if frontier is not None and frontier.audit_rdf() and \
                best_sched is not None and best_mach is not None and \
                cmax(inst, best_sched) == U and \
                check_schedule(inst, U, best_sched, best_mach) and L <= U:
            final_ok = True
        st = dict(self.stats)
        st.update(
            L=L, U=U, opt=U, init_L=init_L, init_U=init_U,
            certified=bool(L == U and final_ok),
            audit=bool(final_ok), proof=bool(final_ok),
            partial_final=bool(final_ok),
            cert_h=(U - 1 if L == U else None),
            total_lp=(st['lp'] + st['cert_lp'] + st['pin_lp']),
            probe_count=probes, queries=probes,
            final=bool(L == U),
            frontier=frontier,
            schedule=list(best_sched) if best_sched is not None else None,
            machine=list(best_mach) if best_mach is not None else None,
            init_schedule=init_sched, init_machine=init_mach,
            W=self.W, cache_cap=self.cache.capacity,
            evict=self.cache.policy,
            cache_hit=self.cache.hits, cache_miss=self.cache.misses,
            cache_evict=self.cache.evictions,
            cache_restores=self.cache.restores,
            cache_partial=self.cache.partial,
            t=round(time.time() - self.t0, 4),
            ok=bool(L == U and final_ok and U == getattr(self, 'known', U)),
        )
        return st


def run_mht(inst, known, name, idx, **kw):
    co = MHT(inst, **kw)
    co.known = known
    r = co.run()
    r.update(name=name, idx=idx, known=known)
    return r
