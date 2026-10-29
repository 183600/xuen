"""v8.6 LNS-ALC: randomized exact-repair large neighborhood search.

The LB side of REST tightens the bracket with infeasible restrictions.
This module adds the dual operator on the UB side.  Given an incumbent
schedule (s, mach) and a target horizon h = UB - 1:

  * remove a random subset R of jobs that contains every job violating h;
  * keep every other job fixed (start and machine);
  * solve the exact restriction of R against the fixed calendars and
    the fixed precedence interfaces with a small MILP;
  * if a schedule at h exists, replay it with check_schedule, install it
    as the new incumbent, and decrement h.

This is optimal-substructure repair: only R is re-optimized, the rest is
a boundary condition.  The randomized destroy step chooses R; the repair
is exact for the chosen R.  A failed repair proves nothing about the
full instance, so only verified schedules are accepted.
"""
import sys
import time
import random

sys.path[:0] = ['exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a',
                'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60',
                'exp/v13']

import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import lil_matrix

from chip import CRISP, chip_bounds
from po import heads_tails
from rdf import check_schedule


def repair_milp(inst, h, R, starts, machs, tlim=0.4):
    """Exact repair of R with every other job fixed.  None = infeasible."""
    p, m, elig = inst['p'], inst['m'], inst['elig']
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    R = set(R)
    fixed = [i for i in range(n) if i not in R]
    for i in fixed:
        if starts[i] + p[i] + q[i] > h:
            return None, None
    idx, cols = {}, []
    for i in R:
        for k in elig[i]:
            for t in range(est[i], h - q[i] - p[i] + 1):
                idx[(i, k, t)] = len(cols)
                cols.append((i, k, t))
    if not cols:
        return None, None
    rows, lo, hi = [], [], []
    for i in R:
        row = {}
        for (ii, k, t), c in idx.items():
            if ii == i:
                row[c] = 1.0
        rows.append(row); lo.append(1.0); hi.append(1.0)
    occ = [[0] * h for _ in range(m)]
    for i in fixed:
        for tau in range(starts[i], min(h, starts[i] + p[i])):
            occ[machs[i]][tau] += 1
    for k in range(m):
        for tau in range(h):
            if occ[k][tau] > 1:
                return None, None
            row = {}
            for (i, kk, t), c in idx.items():
                if kk == k and t <= tau < t + p[i]:
                    row[c] = 1.0
            if row:
                rows.append(row); lo.append(-np.inf)
                hi.append(1.0 - occ[k][tau])
    for i in range(n):
        for j in inst['succ'][i]:
            if i in R and j in R:
                row = {}
                for (ii, k, t), c in idx.items():
                    if ii == i:
                        row[c] = row.get(c, 0) - t
                    if ii == j:
                        row[c] = row.get(c, 0) + t
                rows.append(row); lo.append(p[i]); hi.append(np.inf)
            elif i in R and j not in R:
                row = {}
                for (ii, k, t), c in idx.items():
                    if ii == i:
                        row[c] = t
                rows.append(row); lo.append(-np.inf)
                hi.append(starts[j] - p[i])
            elif i not in R and j in R:
                row = {}
                for (ii, k, t), c in idx.items():
                    if ii == j:
                        row[c] = t
                rows.append(row); lo.append(starts[i] + p[i])
                hi.append(np.inf)
    A = lil_matrix((len(rows), len(cols)))
    for r, row in enumerate(rows):
        for c, v in row.items():
            A[r, c] = v
    res = milp(np.zeros(len(cols)), integrality=np.ones(len(cols)),
               bounds=Bounds(0, 1),
               constraints=LinearConstraint(A.tocsr(), np.array(lo),
                                            np.array(hi)),
               options={'time_limit': tlim, 'presolve': True})
    if res.status != 0:
        return None, None
    z = res.x
    ns, nm = list(starts), list(machs)
    for (i, k, t), c in idx.items():
        if z[c] > 0.5:
            ns[i], nm[i] = t, k
    return ns, nm




def _insert_interval(busy, a, b):
    busy.append((a, b))
    busy.sort()


def _earliest_gap(busy, base, dur, latest):
    t = base
    for a, b in busy:
        if t + dur <= a:
            break
        if t < b:
            t = b
    return t if t + dur <= latest else None


def greedy_repair(inst, h, R, starts, machs, rng, tries=3):
    """Cheap serial-SGS repair before the exact MILP.  None if it fails."""
    p, m, elig = inst['p'], inst['m'], inst['elig']
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    R = set(R)
    fixed = [i for i in range(n) if i not in R]
    busy = [[] for _ in range(m)]
    for i in fixed:
        if starts[i] + p[i] + q[i] > h:
            return None, None
        _insert_interval(busy[machs[i]], starts[i], starts[i] + p[i])
    # fixed predecessor/successor interfaces
    rel = {}
    deadline = {}
    for i in R:
        lo = est[i]
        hi = h - q[i] - p[i]
        for j in inst['pred'][i]:
            if j not in R:
                lo = max(lo, starts[j] + p[j])
        for j in inst['succ'][i]:
            if j not in R:
                hi = min(hi, starts[j] - p[i])
        rel[i], deadline[i] = lo, hi
    # topological order within R
    order = []
    rem = {i: len([j for j in inst['pred'][i] if j in R]) for i in R}
    ready = [i for i in R if rem[i] == 0]
    while ready:
        ready.sort(key=lambda i: (rel[i], -q[i], i))
        i = ready.pop(0)
        order.append(i)
        for j in inst['succ'][i]:
            if j in R:
                rem[j] -= 1
                if rem[j] == 0:
                    ready.append(j)
    if len(order) < len(R):
        return None, None
    for tr in range(tries):
        ns, nm = list(starts), list(machs)
        b2 = [list(x) for x in busy]
        ok = True
        seq = list(order)
        if tr == 1:
            seq.sort(key=lambda i: (-q[i], rel[i], i))
        elif tr >= 2:
            # random tie-breaking on the topological order
            for _ in range(len(seq)):
                a = rng.randrange(len(seq))
                b = rng.randrange(len(seq))
                if rel[seq[a]] == rel[seq[b]]:
                    seq[a], seq[b] = seq[b], seq[a]
        for i in seq:
            base = rel[i]
            for j in inst['pred'][i]:
                if j in R:
                    base = max(base, ns[j] + p[j])
            best = None
            for k in elig[i]:
                t = _earliest_gap(b2[k], base, p[i], deadline[i])
                if t is None:
                    continue
                cand = (t, t + p[i], k)
                if best is None or cand < best:
                    best = cand
            if best is None:
                ok = False
                break
            t, ft, k = best
            ns[i], nm[i] = t, k
            _insert_interval(b2[k], t, ft)
        if ok and check_schedule(inst, h, ns, nm):
            return ns, nm
    return None, None

def lns_drop(inst, ub, starts, machs, budget=40, kmax=14, tlim=0.4,
             stall=8, seed=0):
    """Randomized exact-repair LNS.  Returns (ub, schedule, machine, stats)."""
    rng = random.Random(20261024 + seed * 100003)
    p = inst['p']
    est, q = heads_tails(inst, 0, [0] * inst['n'])
    best, bs, bm = ub, list(starts), list(machs)
    checks = 0
    fail_streak = 0
    t0 = time.time()
    while checks < budget and fail_streak < stall and best > 0:
        h = best - 1
        viol = [i for i in range(inst['n']) if bs[i] + p[i] + q[i] > h]
        if not viol:
            break
        R = set(viol)
        if len(R) > kmax:
            # too many violators: spend one repair on the largest tails
            viol.sort(key=lambda i: bs[i] + p[i] + q[i], reverse=True)
            R = set(viol[:kmax])
        pool = [i for i in range(inst['n']) if i not in R]
        def key(i):
            ov = 0
            for j in viol:
                if not (bs[i] + p[i] <= bs[j] or bs[j] + p[j] <= bs[i]):
                    if set(inst['elig'][i]) & set(inst['elig'][j]):
                        ov += 1
            adj = sum(1 for j in viol
                      if j in inst['succ'][i] or i in inst['succ'][j])
            return (ov + 2 * adj + rng.random(), rng.random())
        pool.sort(key=key, reverse=True)
        k = rng.randint(max(len(R), min(8, inst['n'])), min(kmax, inst['n']))
        R.update(pool[:max(0, k - len(R))])
        ns, nm = greedy_repair(inst, h, R, bs, bm, rng)
        if ns is None:
            ns, nm = repair_milp(inst, h, R, bs, bm, tlim=tlim)
            checks += 1
        else:
            checks += 1
        if ns is not None and check_schedule(inst, h, ns, nm):
            best, bs, bm = h, ns, nm
            fail_streak = 0
        else:
            fail_streak += 1
    return best, bs, bm, dict(checks=checks, t=round(time.time() - t0, 4),
                              stall=fail_streak)


class LNSRISP(CRISP):
    """CRISP bracket + LNS UB drop + CHD oracle."""

    def __init__(self, inst, lns_budget=40, lns_kmax=14, lns_tlim=0.4,
                 lns_seed=0, lns_stall=8, **kw):
        self.lns_budget = lns_budget
        self.lns_kmax = lns_kmax
        self.lns_tlim = lns_tlim
        self.lns_seed = lns_seed
        self.lns_stall = lns_stall
        super().__init__(inst, **kw)

    def initial_bounds(self):
        b = chip_bounds(self.inst)
        self.chip = b
        if not b.get('ok'):
            return b['lb0'], None, None, None
        ub, st, ma, stt = lns_drop(
            self.inst, b['ub'], b['schedule'], b['machine'],
            budget=self.lns_budget, kmax=self.lns_kmax,
            tlim=self.lns_tlim, seed=self.lns_seed, stall=self.lns_stall)
        self.lns = stt
        return b['lb'], ub, st, ma
