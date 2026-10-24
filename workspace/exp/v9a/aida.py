"""v9.0 AIDA-ALC: abstract-interpreted proof DAG with a space budget.

AIDA keeps SAGE's outer bracket, GA upper side and STAB store.  The new
lower-side decision procedure is a *memoized abstract interpretation* over
the lattice of start-time boxes:

  * state   B = product_i [lo_i, hi_i]          (a box)
  * closure gamma(B) = precedence tightening   (a Galois connection)
  * leaf    LP(B) infeasible -> Farkas NO(B)
  * split   B = B_L disjoint-union B_R         (one job interval halved)
  * cache   a down-closed set of NO boxes, represented by its maximal
            antichain; a query B is answered by any cached B' >= B.

The branch search is a chaotic iteration of the monotone transformer
    T(X) = leaves(X) union {B | B_L in X and B_R in X}.
Because the transformer is monotone and the box lattice is finite, the
least fixed point is independent of the evaluation order.  Memoization
is therefore a *sound* form of sharing, not a heuristic: a box proved NO
once is never re-proved, and a box contained in a proved NO box is closed
by the downward closure of the NO set.

The proof object is a DAG, not a tree.  Its nodes are canonical boxes;
a child edge may point to a node with a *larger* box (a subsumption
edge).  The checker verifies the source node at its own box and then uses
B_child subset B_source; this is sound because NO is downward closed.

Space is a first-class budget.  `spacecap` counts distinct proof-DAG
nodes, not recursive calls; `lpcap` counts LP solves.  A failed policy
leaves its completed NO boxes in the arena, so a second policy (a
different chaotic-iteration order) can resume from them.  The final
proof is the union of all completed boxes; no verdict is ever accepted
without an independent replay of the DAG.
"""
import sys
import time
import random

sys.path[:0] = ['exp/v9a', 'exp/v8j', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

import numpy as np
import scipy.sparse as sp
from scipy.optimize import linprog

from apex import Proof
from sage import (SAGE, ga_schedule, SubsumptionProof, _elig_aware)
from prism import (root_box, tighten, box_forbid, _score,
                   DEFAULT_POLICY)
from sdecc import SDLP
from cert import (verify, integer_certificate, DENS, _row_meta)
from rdf import check_schedule
from po import heads_tails

BIG = tuple(range(1, 400)) + (420, 480, 500, 600, 720, 840, 1000,
                              1095, 1200, 1500, 1800, 2000, 2400, 3000,
                              3600, 4000, 5000, 6000, 7200, 10000,
                              12000, 20000, 50000, 100000)


# ------------------------------------------------------------------ helpers
def _subset(a, b):
    """Box a is contained in box b (coordinate-wise)."""
    if a is None:
        return True
    if b is None:
        return False
    alo, ahi = a
    blo, bhi = b
    return all(alo[i] >= blo[i] and ahi[i] <= bhi[i]
               for i in range(len(alo)))


def _key(lo, hi):
    return (tuple(lo), tuple(hi))


def _get_box(node):
    return node.get('box')


def _cert_from_bounds(lp, inst, h, bounds, forbid, dens):
    """Farkas certificate from the shared root matrix with zeroed columns.

    The branch LP and the certificate LP differ only in which start
    columns are present.  Reusing the root matrix avoids rebuilding the
    O(nT) dominance block at every leaf.
    """
    present = [c for c, b in enumerate(bounds) if b != (0, 0)]
    if not present:
        return None
    A = lp.A.tocsr()[:, present]
    hi = lp.hi
    n = lp.n
    n_eq = lp.n_eq
    nr = A.shape[0]
    r = nr - n_eq
    B = sp.hstack([A[:n_eq].T, A[n_eq:].T]).tocsr()
    c = np.zeros(n_eq + r)
    c[:n_eq] = 1.0
    c[n_eq:] = hi[n_eq:]
    A_eq = np.zeros((1, n_eq + r))
    A_eq[0, n_eq:] = 1.0
    bounds_y = [(None, None)] * n_eq + [(0, None)] * r
    res = linprog(c, A_ub=-B, b_ub=np.zeros(len(present)),
                  A_eq=A_eq, b_eq=[1.0], bounds=bounds_y,
                  method='highs')
    if res.status != 0 or res.fun >= 0:
        return None
    meta = _row_meta(lp)
    for D in dens:
        y = np.rint(res.x * D).astype(np.int64)
        ATy = A.T.dot(y)
        bt = int(hi[n:].dot(y[n:])) + int(y[:n].sum())
        if ATy.min() >= 0 and bt < 0:
            yb = y[n:]
            return dict(
                kind='packing', scale=D,
                beta=[(m[1], m[2], int(yb[k]))
                      for k, m in enumerate(meta)
                      if m[0] == 'cap' and yb[k]],
                dom=[(m[1], m[2], m[3], int(yb[k]))
                     for k, m in enumerate(meta)
                     if m[0] == 'dom' and yb[k]],
                exp=[(m[1], m[2], int(yb[k]))
                     for k, m in enumerate(meta)
                     if m[0] == 'exp' and yb[k]],
                alpha=[int(v) for v in y[:n]], obj=bt,
                cuts=[(meta[k], int(yb[k]))
                      for k in range(len(meta)) if yb[k]],
                farkas=res.fun)
    return None


# --------------------------------------------------------------- proof DAG
class AIDAProof(Proof):
    """A self-contained NO(h) proof DAG over canonical boxes."""

    kind = 'branch'

    def __init__(self, inst, h, nodes, root, stats=None):
        super().__init__(inst, h)
        self.nodes = nodes
        self.root = root
        self.stats = stats or {}
        self._valid = {}

    def _node_box(self, nid):
        return self.nodes[nid].get('box')

    def _valid_node(self, nid):
        if nid in self._valid:
            return self._valid[nid]
        self._valid[nid] = False          # cycle guard
        node = self.nodes[nid]
        tag = node['tag']
        box = node.get('box')
        if tag == 'empty':
            ok = True
        elif tag == 'leaf':
            F = box_forbid(self.inst, self.h, box[0], box[1])
            ok = bool(verify(self.inst, self.h, node['cert'], forbid=F))
        elif tag == 'node':
            lo, hi = box
            i, mid = node['i'], node['mid']
            if not (0 <= i < self.inst['n'] and lo[i] <= mid < hi[i]):
                ok = False
            else:
                llo, lhi = list(lo), list(hi)
                lhi[i] = mid
                rlo, rhi = list(lo), list(hi)
                rlo[i] = mid + 1
                lb = tighten(self.inst, self.h, llo, lhi, True)
                rb = tighten(self.inst, self.h, rlo, rhi, True)
                ok = (self._covers(node['left'], lb)
                      and self._covers(node['right'], rb))
        else:
            ok = False
        self._valid[nid] = ok
        return ok

    def _covers(self, nid, expected):
        """Node nid proves NO(box) for a box containing `expected`."""
        if not self._valid_node(nid):
            return False
        stored = self._node_box(nid)
        if expected is None:
            return stored is None
        return _subset(expected, stored)

    def audit_rdf(self):
        try:
            lo, hi = root_box(self.inst, self.h)
            root = tighten(self.inst, self.h, lo, hi, True)
            if root is None:
                return self.nodes[self.root]['tag'] == 'empty'
            return self._covers(self.root, root)
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()

    def size(self):
        nodes = len(self.nodes)
        intervals = sum(self.inst['n'] for _ in self.nodes)
        return dict(nodes=nodes, intervals=intervals,
                    leaves=sum(1 for x in self.nodes if x['tag'] == 'leaf'),
                    empty=sum(1 for x in self.nodes if x['tag'] == 'empty'))


# --------------------------------------------------------------- decision
def aida_branch_decide(inst, h, policies=None, spacecap=512, lpcap=4000,
                       depthcap=24, use_memo=True, use_sub=True,
                       closure=False, cert_dens=BIG, seed=0):
    """Memoized box branch, with a portfolio of evaluation orders.

    Returns dict(verdict, proof, schedule, machine, nodes, leaves, depth,
    lp_solves, cert_lp, memo_hits, sub_hits, dag_nodes, antichain,
    policies_used, t, unknown).
    """
    t0 = time.time()
    n, m, p = inst['n'], inst['m'], inst['p']
    est, q = heads_tails(inst, 0, [0] * n)
    elig = _elig_aware(inst)
    rlo, rhi = root_box(inst, h)
    root = tighten(inst, h, rlo, rhi, closure)
    stats = dict(nodes=0, leaves=0, depth=0, lp_solves=0, cert_lp=0,
                 memo_hits=0, sub_hits=0, dag_nodes=0, antichain=0,
                 policies_used=0, unknown=False, space_hit=False,
                 lp_hit=False)
    if policies is None:
        policies = [dict(DEFAULT_POLICY)]
    if root is None:
        nodes = [dict(tag='empty', box=None)]
        proof = AIDAProof(inst, h, nodes, 0, stats)
        stats.update(dag_nodes=1, policies_used=1,
                     t=round(time.time() - t0, 5))
        return dict(verdict=False, proof=proof, schedule=None,
                    machine=None, **stats)

    lp = SDLP(inst, h, est, q, use_dom=True, elig_aware=elig)
    base = [(0, 1)] * lp.N
    nodes = []
    memo = {}
    no_boxes = []          # maximal NO boxes: [(box, node_id)]
    yes_box = None         # (box, schedule, machine)

    def new_node(tag, box, **kw):
        nd = dict(tag=tag, box=box, **kw)
        nodes.append(nd)
        return len(nodes) - 1

    def find_superset(box):
        best = None
        for b, nid in no_boxes:
            if _subset(box, b):
                if best is None or _subset(b, best[0]):
                    best = (b, nid)
        return best

    def insert_no(box, nid):
        # Existing superset should have been found before solving.
        no_boxes[:] = [(b, x) for b, x in no_boxes if not _subset(b, box)]
        no_boxes.append((box, nid))
        # exact memo is redundant once a maximal NO box covers it
        for k in list(memo):
            if memo[k][0] == 'no' and _subset(k, box):
                del memo[k]
        stats['antichain'] = max(stats['antichain'], len(no_boxes))

    def allowed_times(i, bounds, lo, hi):
        return sorted({key[-1] for c, key in enumerate(lp.cols)
                       if key[0] == i and lo[i] <= key[-1] <= hi[i]
                       and bounds[c] != (0, 0)})

    def job_mass(z, i, times, bounds):
        mass = 0.0
        dist = []
        for tt in times:
            v = 0.0
            for c, key in enumerate(lp.cols):
                if (key[0] == i and key[-1] == tt
                        and bounds[c] != (0, 0)):
                    v += z[c]
            dist.append((tt, v))
            mass += v
        return mass, dist

    def choose(z, bounds, lo, hi, policy, rng):
        cand = []
        for i in range(n):
            times = allowed_times(i, bounds, lo, hi)
            if len(times) <= 1:
                continue
            mass, dist = job_mass(z, i, times, bounds)
            frac = sum(v for _, v in dist if 1e-7 < v < 1 - 1e-7)
            if frac <= 1e-7:
                continue
            score = _score(policy.get('heur', 'frac'), mass, frac,
                           q[i], p[i], hi[i] - lo[i], len(times),
                           len(inst['succ'][i]), len(inst['pred'][i]),
                           len(inst['elig'][i]), i, policy.get('weights'))
            cand.append((score, i, dist, times))
        if not cand:
            return None, None
        cand.sort(reverse=True)
        topk = min(int(policy.get('topk', 1)), len(cand))
        if topk > 1:
            pick = cand[rng.randrange(topk)]
        else:
            pick = cand[0]
        _, i, dist, times = pick
        total = sum(v for _, v in dist)
        split = policy.get('split', 0.5)
        acc = 0.0
        mid = times[0]
        for tt, v in dist:
            acc += v
            if acc >= split * total:
                mid = tt
                break
        left = [tt for tt in times if tt <= mid]
        right = [tt for tt in times if tt > mid]
        if not left or not right:
            mid = times[len(times) // 2 - 1]
            left = [tt for tt in times if tt <= mid]
            right = [tt for tt in times if tt > mid]
        if not left or not right:
            return None, None
        return i, mid

    def leaf_cert(lo, hi, bounds):
        stats['cert_lp'] += 1
        F = box_forbid(inst, h, lo, hi)
        cert = _cert_from_bounds(lp, inst, h, bounds, F, cert_dens)
        if cert is not None and verify(inst, h, cert, forbid=F):
            return cert
        stats['cert_lp'] += 1
        cert = integer_certificate(inst, h, use_dom=True,
                                   elig_aware=elig, forbid=F,
                                   dens=cert_dens)
        if cert is not None and verify(inst, h, cert, forbid=F):
            return cert
        return None

    def integral_schedule(z, bounds):
        starts = [None] * n
        machs = [None] * n
        for c, key in enumerate(lp.cols):
            if bounds[c] == (0, 0):
                continue
            if z[c] > 1 - 1e-7:
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
                    if all(starts[i] + p[i] <= a or starts[i] >= b
                           for a, b in busy[k]):
                        machs[i] = k
                        busy[k].append((starts[i], starts[i] + p[i]))
                        break
                if machs[i] is None:
                    return None
        cmax = max(starts[i] + p[i] for i in range(n))
        if check_schedule(inst, cmax, starts, machs):
            return starts, machs
        return None

    def dfs(lo, hi, depth, policy, rng):
        nonlocal yes_box
        st = tighten(inst, h, lo, hi, closure)
        if st is None:
            nid = new_node('empty', None)
            return ('no', nid)
        lo, hi = st
        box = _key(lo, hi)
        if use_memo and box in memo:
            stats['memo_hits'] += 1
            got = memo[box]
            return got
        if use_sub:
            src = find_superset(box)
            if src is not None:
                stats['sub_hits'] += 1
                return ('no', src[1])
        if depth > depthcap:
            stats['unknown'] = True
            return None
        if len(nodes) >= spacecap:
            stats['space_hit'] = True
            stats['unknown'] = True
            return None
        if stats['lp_solves'] >= lpcap:
            stats['lp_hit'] = True
            stats['unknown'] = True
            return None
        b = list(base)
        for c, key in enumerate(lp.cols):
            i, t = key[0], key[-1]
            if t < lo[i] or t > hi[i]:
                b[c] = (0, 0)
        stats['nodes'] += 1
        stats['lp_solves'] += 1
        res = lp.solve(b)
        if res.status == 2:
            stats['leaves'] += 1
            cert = leaf_cert(lo, hi, b)
            if cert is None:
                stats['unknown'] = True
                return None
            nid = new_node('leaf', box, cert=cert)
            insert_no(box, nid)
            if use_memo:
                memo[box] = ('no', nid)
            return ('no', nid)
        if res.status != 0:
            stats['unknown'] = True
            return None
        z = res.x
        frac = any(b[c] != (0, 0) and 1e-7 < z[c] < 1 - 1e-7
                   for c in range(lp.N))
        if not frac:
            got = integral_schedule(z, b)
            if got is None:
                stats['unknown'] = True
                return None
            if use_memo:
                memo[box] = ('yes', got[0], got[1])
            return ('yes', got[0], got[1])
        i, mid = choose(z, b, lo, hi, policy, rng)
        if i is None:
            stats['unknown'] = True
            return None
        stats['depth'] = max(stats['depth'], depth)
        llo, lhi = list(lo), list(hi)
        lhi[i] = mid
        rlo2, rhi2 = list(lo), list(hi)
        rlo2[i] = mid + 1
        sides = [(llo, lhi, 'L'), (rlo2, rhi2, 'R')]
        order = policy.get('side', 'left')
        if order == 'right':
            sides = [sides[1], sides[0]]
        left_res = right_res = None
        for slo, shi, tag in sides:
            r = dfs(slo, shi, depth + 1, policy, rng)
            if r is None:
                stats['unknown'] = True
                return None
            if r[0] == 'yes':
                if use_memo:
                    memo[box] = r
                return r
            if tag == 'L':
                left_res = r
            else:
                right_res = r
        nid = new_node('node', box, i=i, mid=mid,
                       left=left_res[1], right=right_res[1])
        insert_no(box, nid)
        if use_memo:
            memo[box] = ('no', nid)
        return ('no', nid)

    # -------------------------------------------------------- portfolio
    rng = random.Random(20261024 + seed * 100003)
    result = None
    for pi, policy in enumerate(policies):
        stats['policies_used'] = pi + 1
        result = dfs(root[0], root[1], 0, policy, rng)
        if result is not None:
            break
        # A policy may have exhausted its own budget; the next policy
        # keeps all completed NO boxes and continues.
    stats['dag_nodes'] = len(nodes)
    stats['t'] = round(time.time() - t0, 5)
    if result is None:
        return dict(verdict=None, proof=None, schedule=None,
                    machine=None, **stats)
    if result[0] == 'yes':
        return dict(verdict=True, proof=None, schedule=result[1],
                    machine=result[2], **stats)
    proof = AIDAProof(inst, h, nodes, result[1], stats)
    if not proof.audit_rdf():
        stats['unknown'] = True
        return dict(verdict=None, proof=None, schedule=None,
                    machine=None, **stats)
    return dict(verdict=False, proof=proof, schedule=None,
                machine=None, **stats)


# --------------------------------------------------------------- portfolio
DEFAULT_POLICIES = [
    dict(heur='frac', split=0.5, side='left', closure=False),
    dict(heur='mass', split=0.5, side='right', closure=False),
    dict(heur='tail', split=0.25, side='left', closure=False),
    dict(heur='slack', split=0.5, side='right', closure=False),
]


class AIDA(SAGE):
    def __init__(self, inst, aida_policies=None, aida_spacecap=512,
                 aida_lpcap=4000, aida_depthcap=24, aida_use_memo=True,
                 aida_use_sub=True, aida_closure=None, **kw):
        super().__init__(inst, **kw)
        self.aida_policies = aida_policies or DEFAULT_POLICIES
        self.aida_spacecap = aida_spacecap
        self.aida_lpcap = aida_lpcap
        self.aida_depthcap = aida_depthcap
        self.aida_use_memo = aida_use_memo
        self.aida_use_sub = aida_use_sub
        self.aida_closure = aida_closure
        self.aida_stats = []

    def _run_aida(self, h, closure, spacecap):
        r = aida_branch_decide(
            self.inst, h, policies=self.aida_policies,
            spacecap=spacecap, lpcap=self.aida_lpcap,
            depthcap=self.aida_depthcap, use_memo=self.aida_use_memo,
            use_sub=self.aida_use_sub, closure=closure)
        self.bb_lp += r.get('lp_solves', 0)
        self.cert_lp_total += r.get('cert_lp', 0)
        self.aida_stats.append({k: r.get(k) for k in
                                ('nodes', 'leaves', 'depth', 'lp_solves',
                                 'cert_lp', 'memo_hits', 'sub_hits',
                                 'dag_nodes', 'antichain', 'policies_used',
                                 'space_hit', 'lp_hit', 't')})
        return r

    def _probe(self, h):
        closures = ([self.aida_closure] if self.aida_closure is not None
                    else [True, False])
        r = None
        for k, closure in enumerate(closures):
            cap = (min(self.aida_spacecap, 128)
                   if k == 0 and len(closures) > 1
                   else self.aida_spacecap)
            r = self._run_aida(h, closure, cap)
            if r['verdict'] is not None:
                break
        if r['verdict'] is False:
            self.stats['bb_no'] += 1
            self._record_proof(r['proof'])
            return False, r['proof']
        if r['verdict'] is True and self.bb_yes:
            s, m = r['schedule'], r['machine']
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            if check_schedule(self.inst, h, s, m):
                self.stats['bb_yes'] += 1
                return True, (s, m, cmax)
        if r['verdict'] is True:
            self.stats['bb_yes_ignored'] = \
                self.stats.get('bb_yes_ignored', 0) + 1
        else:
            self.stats['bb_unknown'] += 1
        if self.use_ga:
            got, st = ga_schedule(self.inst, h, pop=self.ga_pop,
                                  gens=self.ga_gens,
                                  budget=self.ga_budget)
            self.ga_stats.append(st)
            if got is not None:
                s, m = got
                cmax = max(s[i] + self.inst['p'][i]
                           for i in range(self.inst['n']))
                self.stats['ga_yes'] += 1
                return True, (s, m, cmax)
            self.stats['ga_no'] += 1
        self.stats['chd_fallback'] += 1
        v, st, rdf = self._decide(h)
        self.queries += 1
        self._absorb(st)
        self._record(h, v, st)
        return v, rdf

def run(cls, inst, known, name, idx, **kw):
    t0 = time.time()
    co = cls(inst, **kw)
    r = co.optimize()
    dt = time.time() - t0
    r.update(name=name, idx=idx, known=known, t=round(dt, 4))
    b = getattr(co, 'chip', None) or {}
    pin = getattr(co, 'pin', None) or {}
    r['chip_lb'] = b.get('lb')
    r['chip_ub'] = b.get('ub')
    r['pin_lb'] = pin.get('lb')
    r['pin_solves'] = pin.get('solves')
    r['pin_lp'] = getattr(co, 'pin_lp', 0)
    r['bb_lp'] = getattr(co, 'bb_lp', 0)
    r['cert_lp'] = getattr(co, 'cert_lp_total', 0)
    r['ga_stats'] = getattr(co, 'ga_stats', [])
    r['proof_kind'] = getattr(getattr(co, 'lb_proof', None),
                              'kind', None)
    r['stats2'] = getattr(co, 'stats', {})
    r['aida'] = getattr(co, 'aida_stats', [])
    r['lns'] = getattr(co, 'lns_stats', None)
    r['ok'] = bool(r['certified'] and r['opt'] == known
                   and r['audit'] and r['proof']
                   and r['cert_h'] == known - 1)
    return r
