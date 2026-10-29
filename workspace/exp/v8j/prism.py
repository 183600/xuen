"""v8.9 PRISM-ALC: proof-carrying interval segment tree.

PRISM keeps SAGE's outer bracket, GA upper side and STAB proof store, but
replaces the explicit forbidden-pair branch proof by an interval state:

  * a branch path is a vector of allowed start intervals [lo_i, hi_i];
  * every split is a range chmin/chmax on one job, i.e. a segment-tree
    descent over that job's time domain;
  * a precedence closure operator propagates lower bounds forward and
    upper bounds backward to a fixed point before every LP solve;
  * a leaf certificate is replayed against the complement of the current
    box, so the proof object stores O(n) intervals per node instead of
    O(nT) forbidden pairs.

The closure is a self-stabilizing repair of the interval state: it only
tightens domains, has a finite ranking function (sum of domain widths),
and its fixed point is unique.  It is used as a filter, never as a
replacement for the LP/Farkas/check_schedule trust boundary.

The branch policy (job score, split quantile, side order) is a
hyperparameter; exp/v8j/tune.py selects it by successive halving, and
exp/v8j/meta.py learns a per-instance portfolio on top of the selected
candidates.  Both meta layers only reorder deterministic proof search;
they cannot change a verdict or a certificate.
"""
import sys
import time
import random

sys.path[:0] = ['exp/v8j', 'exp/v8i', 'exp/v8h', 'exp/v8f', 'exp/v8e',
                'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

import numpy as np

from apex import Proof
from sage import (SAGE, ga_schedule, SubsumptionProof, _elig_aware)
from sdecc import SDLP
from cert import verify, integer_certificate
from rdf import check_schedule
from po import heads_tails


# ------------------------------------------------------------- interval box
def root_box(inst, h):
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    lo = [est[i] for i in range(n)]
    hi = [h - q[i] - inst['p'][i] for i in range(n)]
    return lo, hi


def tighten(inst, h, lo, hi, enabled=True):
    """Longest-path closure of a box; returns None if the box is empty.

    Forward:  s_j >= s_i + p_i  =>  lo_j >= lo_i + p_i.
    Backward: s_i <= s_j - p_i  =>  hi_i <= hi_j - p_i.
    Both are valid for every feasible schedule inside the box.
    """
    n, p = inst['n'], inst['p']
    lo = list(lo)
    hi = list(hi)
    for i in range(n):
        if lo[i] > hi[i]:
            return None
    if not enabled:
        return lo, hi
    for i in range(n):
        if lo[i] > hi[i]:
            return None
        for j in inst['succ'][i]:
            v = lo[i] + p[i]
            if v > lo[j]:
                lo[j] = v
                if lo[j] > hi[j]:
                    return None
    for i in range(n - 1, -1, -1):
        for j in inst['succ'][i]:
            v = hi[j] - p[i]
            if v < hi[i]:
                hi[i] = v
                if lo[i] > hi[i]:
                    return None
    return lo, hi


def box_forbid(inst, h, lo, hi):
    """Forbidden pairs equivalent to the box inside the root domain."""
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


class IntervalBranchProof(Proof):
    """A NO(h) proof whose state is a box of per-job intervals."""

    kind = 'branch'

    def __init__(self, inst, h, tree, stats=None):
        super().__init__(inst, h)
        self.tree = tree
        self.stats = stats or {}

    def _check(self, node, lo, hi):
        st = tighten(self.inst, self.h, lo, hi)
        if st is None:
            return node[0] == 'empty'
        lo, hi = st
        tag = node[0]
        if tag == 'empty':
            return False
        if tag == 'leaf':
            F = box_forbid(self.inst, self.h, lo, hi)
            return bool(verify(self.inst, self.h, node[1], forbid=F))
        if tag != 'node':
            return False
        _, i, mid, left, right = node
        n = self.inst['n']
        if not (0 <= i < n and lo[i] <= mid < hi[i]):
            return False
        llo, lhi = list(lo), list(hi)
        lhi[i] = mid
        rlo, rhi = list(lo), list(hi)
        rlo[i] = mid + 1
        return (self._check(left, llo, lhi)
                and self._check(right, rlo, rhi))

    def audit_rdf(self):
        try:
            lo, hi = root_box(self.inst, self.h)
            return self._check(self.tree, lo, hi)
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()

    def size(self):
        """Number of branch nodes and interval entries (proof economics)."""
        nodes = [0]
        intervals = [0]

        def rec(t, depth):
            nodes[0] += 1
            intervals[0] += self.inst['n']
            if t[0] == 'node':
                rec(t[3], depth + 1)
                rec(t[4], depth + 1)
        rec(self.tree, 0)
        return dict(nodes=nodes[0], intervals=intervals[0],
                    pairs=intervals[0] * 0)


# ------------------------------------------------------------------ policy
DEFAULT_POLICY = dict(heur='mass', split=0.5, side='left',
                      closure=True, weights=None)


def _score(heur, zmass, frac, q, p, slack, width, succ, pred, elig,
           i, weights):
    if heur == 'mass':
        return (zmass, q, succ, -i)
    if heur == 'frac':
        return (frac, zmass, q, succ, -i)
    if heur == 'tail':
        return (q, frac, zmass, succ, -i)
    if heur == 'slack':
        return (slack, frac, zmass, q, -i)
    if heur == 'width':
        return (width, frac, zmass, q, -i)
    if heur == 'succ':
        return (succ, frac, zmass, q, -i)
    if heur == 'linear' and weights is not None:
        (wf, wm, wq, wp, ws, wd, wu, we) = weights
        return (wf * frac + wm * zmass + wq * (q / 10.0)
                + wp * (p / 10.0) + ws * (slack / 10.0)
                + wd * (width / 10.0) + wu * succ + we * elig, -i)
    return (zmass, q, succ, -i)


def interval_branch_decide(inst, h, nodecap=96, depthcap=24, policy=None,
                           seed=0):
    """Self-stabilizing interval LP branch.

    Returns dict(verdict, proof, schedule, machine, nodes, leaves, depth,
    lp_solves, cert_lp, closure_empty, branch_jobs, t).
    verdict False = NO with proof, True = YES with checked schedule,
    None = budget exhausted.
    """
    t0 = time.time()
    n, m, p = inst['n'], inst['m'], inst['p']
    pol = dict(DEFAULT_POLICY)
    if policy:
        pol.update(policy)
    use_closure = bool(pol.get('closure', True))
    elig = _elig_aware(inst)
    rlo, rhi = root_box(inst, h)
    root = tighten(inst, h, rlo, rhi, use_closure)
    stats = dict(nodes=0, leaves=0, depth=0, lp_solves=0,
                 cert_lp=0, branch_jobs=[], closure_empty=0,
                 unknown=False, side_unknown=0)
    if root is None:
        tree = ('empty',)
        proof = IntervalBranchProof(inst, h, tree, stats)
        stats['t'] = round(time.time() - t0, 5)
        return dict(verdict=False, proof=proof, schedule=None,
                    machine=None, **stats)
    rlo, rhi = root
    est0, q0 = heads_tails(inst, 0, [0] * n)
    qeff = [h - rhi[i] - p[i] for i in range(n)]
    lp = SDLP(inst, h, est=rlo, q=qeff, use_dom=True,
              elig_aware=elig)
    base = [(0, 1)] * lp.N

    def solve(bounds):
        stats['nodes'] += 1
        stats['lp_solves'] += 1
        if stats['nodes'] > nodecap:
            stats['unknown'] = True
            return None
        return lp.solve(bounds)

    def allowed_times(i, bounds, lo, hi):
        out = set()
        for c, key in enumerate(lp.cols):
            if key[0] == i and bounds[c] != (0, 0):
                t = key[-1]
                if lo[i] <= t <= hi[i]:
                    out.add(t)
        return sorted(out)

    def job_mass(z, i, times, bounds):
        mass = 0.0
        dist = []
        for tt in times:
            v = 0.0
            for c, key in enumerate(lp.cols):
                if key[0] == i and key[-1] == tt and bounds[c] != (0, 0):
                    v += z[c]
            dist.append((tt, v))
            mass += v
        return mass, dist

    def choose(z, bounds, lo, hi):
        cand = []
        for i in range(n):
            times = allowed_times(i, bounds, lo, hi)
            if len(times) <= 1:
                continue
            mass, dist = job_mass(z, i, times, bounds)
            frac = sum(v for _, v in dist if 1e-7 < v < 1 - 1e-7)
            if frac <= 1e-7:
                continue
            score = _score(pol['heur'], mass, frac, q0[i],
                           p[i], hi[i] - lo[i], len(times),
                           len(inst['succ'][i]), len(inst['pred'][i]),
                           len(inst['elig'][i]), i, pol.get('weights'))
            cand.append((score, i, dist, times))
        if not cand:
            return None, None, None
        cand.sort(reverse=True)
        _, i, dist, times = cand[0]
        total = sum(v for _, v in dist)
        acc = 0.0
        mid = times[0]
        for tt, v in dist:
            acc += v
            if acc >= pol.get('split', 0.5) * total:
                mid = tt
                break
        left = [tt for tt in times if tt <= mid]
        right = [tt for tt in times if tt > mid]
        if not left or not right:
            mid = times[len(times) // 2 - 1]
            left = [tt for tt in times if tt <= mid]
            right = [tt for tt in times if tt > mid]
        if not left or not right:
            return None, None, None
        return i, mid, times

    def leaf_cert(lo, hi):
        stats['cert_lp'] += 1
        F = box_forbid(inst, h, lo, hi)
        cert = integer_certificate(inst, h, use_dom=True,
                                   elig_aware=elig, forbid=F)
        if cert is not None and verify(inst, h, cert, forbid=F):
            return ('leaf', cert)
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

    def dfs(lo, hi, depth):
        st = tighten(inst, h, lo, hi, use_closure)
        if st is None:
            stats['closure_empty'] += 1
            return ('empty',)
        lo, hi = st
        if depth > depthcap:
            stats['unknown'] = True
            return None
        b = list(base)
        for c, key in enumerate(lp.cols):
            i, t = key[0], key[-1]
            if t < lo[i] or t > hi[i]:
                b[c] = (0, 0)
        res = solve(b)
        if res is None:
            return None
        if res.status == 2:
            stats['leaves'] += 1
            node = leaf_cert(lo, hi)
            if node is None:
                stats['unknown'] = True
            return node
        if res.status != 0:
            stats['unknown'] = True
            return None
        z = res.x
        frac = False
        for c, key in enumerate(lp.cols):
            if b[c] != (0, 0) and 1e-7 < z[c] < 1 - 1e-7:
                frac = True
                break
        if not frac:
            got = integral_schedule(z, b)
            if got is None:
                stats['unknown'] = True
                return None
            return ('yes', got[0], got[1])
        i, mid, times = choose(z, b, lo, hi)
        if i is None:
            stats['unknown'] = True
            return None
        stats['depth'] = max(stats['depth'], depth)
        stats['branch_jobs'].append((i, mid))
        llo, lhi = list(lo), list(hi)
        lhi[i] = mid
        rlo2, rhi2 = list(lo), list(hi)
        rlo2[i] = mid + 1
        sides = [('L', llo, lhi, left_mass(z, i, mid, times, b)),
                 ('R', rlo2, rhi2, right_mass(z, i, mid, times, b))]
        order = pol.get('side', 'left')
        if order == 'right':
            sides = [sides[1], sides[0]]
        elif order == 'mass':
            sides.sort(key=lambda x: -x[3])
        children = {}
        unknown = False
        for tag, slo, shi, _ in sides:
            r = dfs(slo, shi, depth + 1)
            if r is None:
                unknown = True
                continue
            if r[0] == 'yes':
                return r
            children[tag] = r
        if unknown:
            stats['side_unknown'] += 1
            return None
        return ('node', i, mid, children['L'], children['R'])

    def left_mass(z, i, mid, times, bounds):
        return job_mass(z, i, [t for t in times if t <= mid], bounds)[0]

    def right_mass(z, i, mid, times, bounds):
        return job_mass(z, i, [t for t in times if t > mid], bounds)[0]

    tree = dfs(rlo, rhi, 0)
    stats['t'] = round(time.time() - t0, 5)
    if tree is None:
        return dict(verdict=None, proof=None, schedule=None,
                    machine=None, **stats)
    if tree[0] == 'yes':
        return dict(verdict=True, proof=None, schedule=tree[1],
                    machine=tree[2], **stats)
    proof = IntervalBranchProof(inst, h, tree, stats)
    if not proof.audit_rdf():
        stats['unknown'] = True
        return dict(verdict=None, proof=None, schedule=None,
                    machine=None, **stats)
    return dict(verdict=False, proof=proof, schedule=None, machine=None,
                **stats)


# ------------------------------------------------------------------- PRISM
class PRISM(SAGE):
    def __init__(self, inst, branch_policy=None, **kw):
        super().__init__(inst, **kw)
        self.branch_policy = branch_policy or dict(DEFAULT_POLICY)

    def _probe(self, h):
        if self.use_bb:
            r = interval_branch_decide(self.inst, h,
                                       nodecap=self.bb_nodecap,
                                       depthcap=self.bb_depthcap,
                                       policy=self.branch_policy)
            self.bb_lp += r['lp_solves']
            self.cert_lp_total += r.get('cert_lp', 0)
            self.branch_last = r
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
    p = getattr(co, 'pin', None) or {}
    r['chip_lb'] = b.get('lb')
    r['chip_ub'] = b.get('ub')
    r['pin_lb'] = p.get('lb')
    r['pin_solves'] = p.get('solves')
    r['pin_lp'] = getattr(co, 'pin_lp', 0)
    r['bb_lp'] = getattr(co, 'bb_lp', 0)
    r['cert_lp'] = getattr(co, 'cert_lp_total', 0)
    r['ga_stats'] = getattr(co, 'ga_stats', [])
    r['proof_kind'] = getattr(getattr(co, 'lb_proof', None),
                              'kind', None)
    r['stats2'] = getattr(co, 'stats', {})
    r['lns'] = getattr(co, 'lns_stats', None)
    r['ok'] = bool(r['certified'] and r['opt'] == known
                   and r['audit'] and r['proof']
                   and r['cert_h'] == known - 1)
    return r
