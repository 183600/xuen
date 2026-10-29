"""v9.1 AID-Frontier: an operational, abstract-interpreted DFS frontier.

This module is the live multi-leaf companion of ICF-PACT.  A search state
is a partition tree over the start-time box lattice.  Open leaves carry a
local lower bound; closed leaves carry a concrete NO proof (empty domain,
critical-path bound, or Farkas).  The tree is exactly a partial
certificate: at any budget it can be audited, and if all leaves close the
tree is a NO(h) proof.

The search order is depth-first; the abstract domain is the interval box
with precedence closure from PRISM.  Every transition is a rule of the
small-step operational semantics documented in the artifact.
"""
import sys
import time

sys.path[:0] = ['exp/v9ai', 'exp/v9a', 'exp/v8j', 'exp/v8u', 'exp/v8o',
                'exp/v8i', 'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g',
                'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a',
                'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60',
                'exp/v13']

from apex import Proof
from sage import _elig_aware, _domain
from sdecc import SDLP
from cert import verify, integer_certificate
from rdf import check_schedule
from po import heads_tails
from prism import root_box, tighten, box_forbid
from aida import _cert_from_bounds, BIG


# --------------------------------------------------------------- utilities
def _key(lo, hi):
    return (tuple(lo), tuple(hi))


def _cmax(inst, starts):
    return max(starts[i] + inst['p'][i] for i in range(inst['n']))


def _integral_schedule(inst, lp, z, bounds, elig):
    n, m = inst['n'], inst['m']
    starts = [None] * n
    machs = [None] * n
    for c, key in enumerate(lp.cols):
        if bounds[c] == (0, 0) or z[c] <= 1 - 1e-7:
            continue
        i, t = key[0], key[-1]
        if starts[i] is not None:
            return None
        starts[i] = t
        if elig:
            machs[i] = key[1]
    if any(x is None for x in starts):
        return None
    if not elig:
        busy = [[] for _ in range(m)]
        for i in sorted(range(n), key=lambda i: (starts[i], i)):
            for k in inst['elig'][i]:
                if all(starts[i] + inst['p'][i] <= a or starts[i] >= b
                       for a, b in busy[k]):
                    machs[i] = k
                    busy[k].append((starts[i], starts[i] + inst['p'][i]))
                    break
            if machs[i] is None:
                return None
    if _cmax(inst, starts) > lp.T:
        return None
    if check_schedule(inst, _cmax(inst, starts), starts, machs):
        return starts, machs
    return None


def _choose(lp, z, bounds, lo, hi, policy):
    n = lp.inst['n']
    split = policy.get('split', 0.5)
    best = None
    for i in range(n):
        times = sorted({key[-1] for c, key in enumerate(lp.cols)
                        if key[0] == i and lo[i] <= key[-1] <= hi[i]
                        and bounds[c] != (0, 0)})
        if len(times) <= 1:
            continue
        dist = []
        frac = 0.0
        mass = 0.0
        for t in times:
            v = sum(z[c] for c, key in enumerate(lp.cols)
                    if key[0] == i and key[-1] == t
                    and bounds[c] != (0, 0))
            dist.append((t, v))
            mass += v
            if 1e-7 < v < 1 - 1e-7:
                frac += v
        if frac <= 1e-7:
            continue
        score = (mass, frac)
        if best is None or score > best[0]:
            best = (score, i, dist, times)
    if best is None:
        return None, None
    _, i, dist, times = best
    total = sum(v for _, v in dist)
    acc = 0.0
    mid = times[0]
    for t, v in dist:
        acc += v
        if acc >= split * total:
            mid = t
            break
    left = [t for t in times if t <= mid]
    right = [t for t in times if t > mid]
    if not left or not right:
        mid = times[len(times) // 2 - 1]
        left = [t for t in times if t <= mid]
        right = [t for t in times if t > mid]
    if not left or not right:
        return None, None
    return i, mid


# -------------------------------------------------------------- tree nodes
class Open:
    __slots__ = ('lo', 'hi', 'lb', 'depth')

    def __init__(self, lo, hi, lb, depth):
        self.lo, self.hi = list(lo), list(hi)
        self.lb = int(lb)
        self.depth = depth


class Closed:
    __slots__ = ('lo', 'hi', 'kind', 'cert', 'lb', 'why')

    def __init__(self, lo, hi, kind, cert=None, lb=None, why=None):
        self.lo, self.hi = list(lo), list(hi)
        self.kind = kind
        self.cert = cert
        self.lb = lb
        self.why = why


class Split:
    __slots__ = ('lo', 'hi', 'job', 'mid', 'left', 'right', 'depth')

    def __init__(self, lo, hi, job, mid, left, right, depth):
        self.lo, self.hi = list(lo), list(hi)
        self.job, self.mid = job, mid
        self.left, self.right = left, right
        self.depth = depth


def leaves(node):
    if isinstance(node, Split):
        return leaves(node.left) + leaves(node.right)
    return [node]


def open_leaves(node):
    return [x for x in leaves(node) if isinstance(x, Open)]


class AIDFrontierProof(Proof):
    """A NO(h) proof represented as a partition tree over interval boxes."""
    kind = 'aid-frontier'

    def __init__(self, inst, h, tree, stats=None, box_h=None):
        super().__init__(inst, h)
        self.tree = tree
        self.stats = stats or {}
        self.box_h = int(h if box_h is None else box_h)

    def _check(self, node, expected=None):
        if isinstance(node, Split):
            lo, hi = node.lo, node.hi
            if expected is not None:
                lo, hi = expected
            st = tighten(self.inst, self.box_h, lo, hi)
            if st is None:
                return False
            lo, hi = st
            i, mid = node.job, node.mid
            if not (0 <= i < self.inst['n'] and lo[i] <= mid < hi[i]):
                return False
            llo, lhi = list(lo), list(hi)
            lhi[i] = mid
            rlo, rhi = list(lo), list(hi)
            rlo[i] = mid + 1
            return (self._check(node.left, (llo, lhi))
                    and self._check(node.right, (rlo, rhi)))
        if isinstance(node, Open):
            return False
        return _audit_closed(self.inst, self.h, node, expected,
                             box_h=self.box_h)

    def audit_rdf(self):
        try:
            box = root_box(self.inst, self.box_h)
            st = tighten(self.inst, self.box_h, box[0], box[1], True)
            if st is None:
                return isinstance(self.tree, Closed) and \
                    self.tree.kind == 'empty'
            return self._check(self.tree, st)
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


class LiftedFrontierProof(Proof):
    """NO(target) from a frontier computed at source_h >= target.

    Closed Farkas/empty leaves replay at source_h; horizon monotonicity
    then gives NO(target).  Open leaves are closed by their local
    critical-path lower bound.  This is the proof that lets a suspended
    DFS advance the outer lower bound without completing the probe.
    """
    kind = 'aid-lift'

    def __init__(self, inst, target, source_h, tree, stats=None,
                 box_h=None):
        super().__init__(inst, target)
        self.source_h = int(source_h)
        self.tree = tree
        self.stats = stats or {}
        self.box_h = int(source_h if box_h is None else box_h)

    def _check(self, node, expected=None):
        h = self.source_h
        if isinstance(node, Split):
            lo, hi = node.lo, node.hi
            if expected is not None:
                lo, hi = expected
            st = tighten(self.inst, self.box_h, lo, hi)
            if st is None:
                return False
            lo, hi = st
            i, mid = node.job, node.mid
            if not (0 <= i < self.inst['n'] and lo[i] <= mid < hi[i]):
                return False
            llo, lhi = list(lo), list(hi)
            lhi[i] = mid
            rlo, rhi = list(lo), list(hi)
            rlo[i] = mid + 1
            return (self._check(node.left, (llo, lhi))
                    and self._check(node.right, (rlo, rhi)))
        if isinstance(node, Open):
            lo, hi = node.lo, node.hi
            if expected is not None:
                lo, hi = expected
            st = tighten(self.inst, self.box_h, lo, hi)
            if st is None:
                return False
            lo, hi = st
            return _local_lb(self.inst, lo, hi) > self.h
        # Closed leaf
        if node.kind in ('farkas', 'packing'):
            if h < self.h:
                return False
            lo, hi = node.lo, node.hi
            if expected is not None:
                lo, hi = expected
            st = tighten(self.inst, self.box_h, lo, hi)
            if st is None:
                return False
            lo, hi = st
            F = box_forbid(self.inst, h, lo, hi)
            return bool(verify(self.inst, h, node.cert, forbid=F))
        if node.kind == 'bound':
            lo, hi = node.lo, node.hi
            if expected is not None:
                lo, hi = expected
            lb = _local_lb(self.inst, lo, hi)
            return int(node.lb) == lb and lb > self.h
        if node.kind == 'empty':
            lo, hi = node.lo, node.hi
            if expected is not None:
                lo, hi = expected
            return tighten(self.inst, self.h, lo, hi) is None
        return False

    def audit_rdf(self):
        try:
            if self.source_h < self.h:
                return False
            box = root_box(self.inst, self.box_h)
            st = tighten(self.inst, self.box_h, box[0], box[1], True)
            if st is None:
                return isinstance(self.tree, Closed) and \
                    self.tree.kind == 'empty'
            return self._check(self.tree, st)
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


class PartialFrontierCertificate:
    """A frontier with a global scheduling upper bound U and local L."""
    kind = 'aid-partial-frontier'

    def __init__(self, inst, h, L, U, schedule, machine, tree,
                 box_h=None):
        self.inst = inst
        self.h = int(h)
        self.bbox_h = int(h if box_h is None else box_h)
        self.L = int(L)
        self.U = int(U)
        self.schedule = list(schedule) if schedule is not None else None
        self.machine = list(machine) if machine is not None else None
        self.tree = tree

    def _sched_ok(self):
        if self.schedule is None or self.machine is None:
            return False
        c = _cmax(self.inst, self.schedule)
        return c == self.U and bool(check_schedule(
            self.inst, c, self.schedule, self.machine))

    def audit_rdf(self):
        try:
            if not self._sched_ok():
                return False
            if self.L > self.U:
                return False
            # Every leaf is either closed soundly or open with its local
            # lower bound at least the recorded one.
            for x in leaves(self.tree):
                if isinstance(x, Closed):
                    if not _audit_closed(self.inst, self.h, x,
                                         box_h=self.bbox_h):
                        return False
                else:
                    st = tighten(self.inst, self.bbox_h, x.lo, x.hi, True)
                    if st is None:
                        return False
                    lo, hi = st
                    lb = _local_lb(self.inst, lo, hi)
                    if lb < x.lb:
                        return False
            # L is exactly the minimum local bound.
            lbs = []
            for x in leaves(self.tree):
                if isinstance(x, Open):
                    lbs.append(x.lb)
                else:
                    lbs.append(self.h + 1 if x.kind != 'bound'
                               else int(x.lb))
            return (min(lbs) == self.L) and (self.L <= self.U)
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


def _local_lb(inst, lo, hi):
    q = heads_tails(inst, 0, [0] * inst['n'])[1]
    return max(lo[i] + inst['p'][i] + q[i] for i in range(inst['n']))


def _audit_closed(inst, h, node, expected=None, box_h=None):
    bh = h if box_h is None else box_h
    lo, hi = node.lo, node.hi
    if expected is not None:
        lo, hi = expected
    st = tighten(inst, bh, lo, hi)
    if st is None:
        return node.kind == 'empty'
    lo, hi = st
    if node.kind == 'empty':
        return tighten(inst, h, lo, hi) is None
    if node.kind == 'bound':
        lb = _local_lb(inst, lo, hi)
        return int(node.lb) == lb and lb > h
    if node.kind in ('farkas', 'packing'):
        F = box_forbid(inst, h, lo, hi)
        return bool(verify(inst, h, node.cert, forbid=F))
    return False


# ---------------------------------------------------------------- search
class FrontierSearch:
    def __init__(self, inst, h, budget=64, policy=None, order='left',
                 box_h=None):
        self.inst = inst
        self.h = int(h)
        self.box_h = int(h if box_h is None else box_h)
        self.budget = int(budget)
        self.policy = dict(policy or {})
        self.order = order
        self.stats = dict(lp_solves=0, cert_lp=0, nodes=0, closed=0,
                          empty_closed=0, bound_closed=0,
                          farkas_closed=0, opens=0, splits=0,
                          max_depth=0, budget_hit=False, t=0.0)
        self.elig = _elig_aware(inst)
        self.est, self.q = heads_tails(inst, 0, [0] * inst['n'])
        box = root_box(inst, self.box_h)
        self.root_box = box
        self.lp = None
        self.tree = None
        self.verdict = None
        self.schedule = self.machine = None

    def _solve(self, lo, hi):
        if self.lp is None:
            self.lp = SDLP(self.inst, self.h, self.est, self.q,
                           use_dom=True, elig_aware=self.elig)
        b = [(0, 1)] * self.lp.N
        for c, key in enumerate(self.lp.cols):
            t = key[-1]
            if t < lo[key[0]] or t > hi[key[0]]:
                b[c] = (0, 0)
        self.stats['nodes'] += 1
        self.stats['lp_solves'] += 1
        return b, self.lp.solve(b)

    def _leaf_cert(self, lo, hi, bounds):
        F = box_forbid(self.inst, self.h, lo, hi)
        self.stats['cert_lp'] += 1
        cert = _cert_from_bounds(self.lp, self.inst, self.h, bounds,
                                 F, BIG)
        if cert is not None and verify(self.inst, self.h, cert,
                                       forbid=F):
            return cert
        self.stats['cert_lp'] += 1
        cert = integer_certificate(self.inst, self.h, use_dom=True,
                                   elig_aware=self.elig, forbid=F,
                                   dens=BIG)
        if cert is not None and verify(self.inst, self.h, cert,
                                       forbid=F):
            return cert
        return None

    def _dfs(self, lo, hi, depth):
        st = tighten(self.inst, self.box_h, lo, hi, True)
        if st is None:
            self.stats['closed'] += 1
            self.stats['empty_closed'] += 1
            return Closed(lo, hi, 'empty')
        lo, hi = st
        lb = _local_lb(self.inst, lo, hi)
        if lb > self.h:
            self.stats['closed'] += 1
            self.stats['bound_closed'] += 1
            return Closed(lo, hi, 'bound', lb=lb)
        if self.budget <= 0:
            self.stats['opens'] += 1
            self.stats['budget_hit'] = True
            return Open(lo, hi, lb, depth)
        self.budget -= 1
        self.stats['max_depth'] = max(self.stats['max_depth'], depth)
        b, res = self._solve(lo, hi)
        if res.status == 2:
            cert = self._leaf_cert(lo, hi, b)
            self.stats['closed'] += 1
            self.stats['farkas_closed'] += 1
            if cert is None:
                return Open(lo, hi, lb, depth)
            return Closed(lo, hi, 'farkas', cert=cert)
        if res.status != 0:
            self.stats['opens'] += 1
            return Open(lo, hi, lb, depth)
        z = res.x
        frac = any(b[c] != (0, 0) and 1e-7 < z[c] < 1 - 1e-7
                   for c in range(self.lp.N))
        if not frac:
            got = _integral_schedule(self.inst, self.lp, z, b, self.elig)
            if got is not None:
                self.schedule, self.machine = got
                self.verdict = True
                return None
        i, mid = _choose(self.lp, z, b, lo, hi, self.policy)
        if i is None:
            self.stats['opens'] += 1
            return Open(lo, hi, lb, depth)
        self.stats['splits'] += 1
        llo, lhi = list(lo), list(hi)
        lhi[i] = mid
        rlo, rhi = list(lo), list(hi)
        rlo[i] = mid + 1
        if self.order == 'right':
            r = self._dfs(rlo, rhi, depth + 1)
            if self.verdict is True:
                return None
            l = self._dfs(llo, lhi, depth + 1)
        else:
            l = self._dfs(llo, lhi, depth + 1)
            if self.verdict is True:
                return None
            r = self._dfs(rlo, rhi, depth + 1)
        if self.verdict is True:
            return None
        return Split(lo, hi, i, mid, l, r, depth)

    def run(self):
        t0 = time.time()
        st = tighten(self.inst, self.box_h, *self.root_box, True)
        if st is None:
            self.tree = Closed(self.root_box[0], self.root_box[1],
                               'empty')
            self.verdict = False
        else:
            self.lo, self.hi = st
            self.tree = self._dfs(st[0], st[1], 0)
            if self.verdict is True:
                self.tree = None
            elif self.tree is not None and \
                    all(isinstance(x, Closed) for x in leaves(self.tree)):
                self.verdict = False
        self.stats['t'] = round(time.time() - t0, 5)
        self.stats['leaves'] = 0 if self.tree is None else len(
            leaves(self.tree))
        self.stats['open_leaves'] = 0 if self.tree is None else len(
            open_leaves(self.tree))
        self.stats['L'] = self.local_L()
        return self

    def local_L(self):
        if self.tree is None:
            return self.h + 1
        lbs = []
        for x in leaves(self.tree):
            if isinstance(x, Open):
                lbs.append(x.lb)
            elif isinstance(x, Closed):
                lbs.append(x.lb if x.kind == 'bound' else self.h + 1)
        return min(lbs) if lbs else self.h + 1

    def proof(self):
        if self.verdict is not False:
            return None
        return AIDFrontierProof(self.inst, self.h, self.tree,
                                self.stats, box_h=self.box_h)


def search(inst, h, budget=64, policy=None, order='left', box_h=None):
    return FrontierSearch(inst, h, budget, policy, order,
                          box_h=box_h).run()
