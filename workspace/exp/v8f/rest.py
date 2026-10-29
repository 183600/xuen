"""v8.5 REST-ALC: randomized exact-subproblem tightening.

CRISP (v8.1) closes the bracket with cheap window/energy NOs and four
greedy UB orders.  Its residual gap is integrality/precedence: at
h = OPT-1 the full instance is infeasible, but no window/energy rule
fires.  REST searches for a *small restriction* that is already
infeasible at h:

    for S subset of jobs, I[S] keeps the original est/q and the
    induced precedence.  A feasible schedule of I restricts to a
    feasible schedule of I[S]; hence OPT(I[S]) <= OPT(I), and
    I[S] infeasible at h  =>  OPT(I) > h.

The family of infeasible subsets is an up-set (adding jobs cannot help),
and infeasibility is monotone in h.  REST grows a random core: when the
core is infeasible at h it lifts h and keeps the core; when it becomes
feasible it adds jobs that conflict with the core; when the core reaches
the size cap it restarts.  Every accepted NO is replayed by the exact
subproblem checker (a bounded MILP in this prototype); UNKNOWN never
lifts h.
"""
import sys
import json
import time
import random
from functools import lru_cache

sys.path[:0] = ['exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a',
                'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60',
                'exp/v13']

import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import lil_matrix

from chip import CRISP, chip_bounds, base_corpus, pert_corpus, stress_corpus
from po import heads_tails


# ----------------------------------------------------------- subproblem
def _sub_model(inst, h, jobs):
    """Time-indexed MILP for the restriction I[jobs] at horizon h.

    est/q are the *original* heads/tails.  Only precedence edges with
    both endpoints in jobs are kept.  Returns (A, lo, hi, nvar) or None
    when a window is already empty.
    """
    p, m, elig = inst['p'], inst['m'], inst['elig']
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    idx = {}
    cols = []
    for i in jobs:
        for k in elig[i]:
            for t in range(est[i], h - q[i] - p[i] + 1):
                idx[(i, k, t)] = len(cols)
                cols.append((i, k, t))
    if not cols:
        return None
    rows, lo, hi = [], [], []
    for i in jobs:
        row = {}
        for (ii, k, t), c in idx.items():
            if ii == i:
                row[c] = 1.0
        rows.append(row); lo.append(1.0); hi.append(1.0)
    for k in range(m):
        for tau in range(h):
            row = {}
            for (i, kk, t), c in idx.items():
                if kk == k and t <= tau < t + p[i]:
                    row[c] = 1.0
            if row:
                rows.append(row); lo.append(-np.inf); hi.append(1.0)
    S = set(jobs)
    for i in jobs:
        for j in inst['succ'][i]:
            if j in S:
                row = {}
                for (ii, k, t), c in idx.items():
                    if ii == i:
                        row[c] = row.get(c, 0) - t
                    if ii == j:
                        row[c] = row.get(c, 0) + t
                rows.append(row); lo.append(p[i]); hi.append(np.inf)
    A = lil_matrix((len(rows), len(cols)))
    for r, row in enumerate(rows):
        for c, v in row.items():
            A[r, c] = v
    return A.tocsr(), np.asarray(lo), np.asarray(hi), len(cols)


def sub_feas(inst, h, jobs, tlim=0.4):
    """Exact(ish) restriction checker: 1 NO, 0 YES, -1 UNKNOWN."""
    model = _sub_model(inst, h, jobs)
    if model is None:
        return 1
    A, lo, hi, nv = model
    res = milp(np.zeros(nv), integrality=np.ones(nv),
               bounds=Bounds(0, 1),
               constraints=LinearConstraint(A, lo, hi),
               options={'time_limit': tlim, 'presolve': True})
    if res.status == 2:
        return 1
    if res.status == 0:
        return 0
    return -1


def verify_sub_no(inst, h, jobs, tlim=0.4):
    """Independent replay of a REST NO (fresh solver run)."""
    return sub_feas(inst, h, jobs, tlim=tlim) == 1


# --------------------------------------------------------------- sampling
def _windows(inst, h):
    est, q = heads_tails(inst, 0, [0] * inst['n'])
    lst = [h - q[i] - inst['p'][i] for i in range(inst['n'])]
    return est, lst, q


def _score_job(inst, est, lst, i, core):
    p = inst['p']
    slack = lst[i] - est[i]
    ov = sum(1 for j in core
             if not (lst[i] < est[j] or lst[j] < est[i]))
    adj = sum(1 for j in core
              if j in inst['succ'][i] or i in inst['succ'][j])
    return (10.0 / (1.0 + max(0, slack)) + ov + 2 * adj)


def _sample_core(inst, h, k, rng, est, lst):
    """Mixture of uniform, conflict-BFS, and precedence-BFS cores."""
    n = inst['n']
    mode = rng.random()
    if mode < 0.34:
        return set(rng.sample(range(n), min(n, k)))
    seed = rng.randrange(n)
    core = {seed}
    # scores favor tight/conflicting jobs
    while len(core) < min(n, k):
        pool = [i for i in range(n) if i not in core]
        if not pool:
            break
        if mode < 0.67:
            def key(i):
                ov = sum(1 for j in core
                         if not (lst[i] < est[j] or lst[j] < est[i])
                         and set(inst['elig'][i]) & set(inst['elig'][j]))
                adj = sum(1 for j in core
                          if j in inst['succ'][i] or i in inst['succ'][j])
                slack = lst[i] - est[i]
                return (ov + 2 * adj + 1.0 / (1.0 + max(0, slack)),
                        rng.random())
        else:
            def key(i):
                adj = sum(1 for j in core
                          if j in inst['succ'][i] or i in inst['succ'][j])
                return (3 * adj + rng.random(), rng.random())
        pool.sort(key=key, reverse=True)
        take = min(len(pool), rng.choice([1, 2, 3]))
        core.update(pool[:take])
    return core


def _grow_core(inst, h, core, K, rng, est, lst):
    """Add a few jobs most likely to make the restriction infeasible."""
    n = inst['n']
    pool = [i for i in range(n) if i not in core]
    if not pool:
        return core
    def key(i):
        slack = lst[i] - est[i]
        ov = sum(1 for j in core
                 if not (lst[i] < est[j] or lst[j] < est[i])
                 and set(inst['elig'][i]) & set(inst['elig'][j]))
        adj = sum(1 for j in core
                  if j in inst['succ'][i] or i in inst['succ'][j])
        return (10.0 / (1.0 + max(0, slack)) + ov + 2 * adj, rng.random())
    pool.sort(key=key, reverse=True)
    add = pool[:min(len(pool), max(1, min(3, K - len(core))),
                    rng.choice([1, 2, 3]))]
    return set(core) | set(add)


# --------------------------------------------------------------- REST lift
def rest_lift(inst, lb, ub, K=12, budget=60, tlim=0.4, seed=0,
              early_stop=0):
    """Lift LB by randomized nested restrictions.  Returns a dict."""
    rng = random.Random(20261024 + seed * 100003)
    h = lb
    core = set()
    checks = 0
    lifts = 0
    unk = 0
    restarts = 0
    streak = 0
    certs = []
    sizes = []
    t0 = time.time()
    while h < ub and checks < budget:
        est, lst, _ = _windows(inst, h)
        if core:
            v = sub_feas(inst, h, sorted(core), tlim=tlim)
            checks += 1
            if v == 1:
                if not verify_sub_no(inst, h, sorted(core), tlim=tlim):
                    unk += 1
                    core = set()
                    continue
                certs.append(dict(h=h, jobs=sorted(core)))
                sizes.append(len(core))
                lifts += 1
                h += 1
                streak = 0
                continue
            if v == -1:
                unk += 1
                core = set()
                continue
            # core feasible at h: grow it
            if len(core) < min(inst['n'], K):
                core = _grow_core(inst, h, core, K, rng, est, lst)
                streak += 1
                if early_stop and streak >= early_stop:
                    break
                continue
            core = set()
            restarts += 1
            streak += 1
            if early_stop and streak >= early_stop:
                break
            continue
        # no active core: sample a fresh one
        k = rng.choice([8, 9, 10, 11, 12])
        k = min(inst['n'], max(8, min(K, k)))
        core = _sample_core(inst, h, k, rng, est, lst)
        streak += 1
        if early_stop and streak >= early_stop:
            break
    return dict(lb=h, lifts=lifts, checks=checks, unk=unk,
                restarts=restarts, certs=certs, sizes=sizes,
                t=round(time.time() - t0, 4),
                budget_exhausted=(checks >= budget and h < ub))


# ------------------------------------------------------------------ outer
class RESTCRISP(CRISP):
    """CRISP bracket + REST LB lift + CHD oracle."""

    def __init__(self, inst, K=12, budget=60, tlim=0.4, seed=0,
                 early_stop=0, **kw):
        self.K = K
        self.rest_budget = budget
        self.rest_tlim = tlim
        self.rest_seed = seed
        self.rest_early = early_stop
        super().__init__(inst, **kw)

    def initial_bounds(self):
        b = chip_bounds(self.inst)
        self.chip = b
        if not b.get('ok'):
            return b['lb0'], None, None, None
        r = rest_lift(self.inst, b['lb'], b['ub'], K=self.K,
                      budget=self.rest_budget, tlim=self.rest_tlim,
                      seed=self.rest_seed, early_stop=self.rest_early)
        self.rest = r
        return r['lb'], b['ub'], b['schedule'], b['machine']


def run_rest(inst, known, name, idx, **kw):
    t0 = time.time()
    co = RESTCRISP(inst, **kw)
    r = co.optimize()
    dt = time.time() - t0
    r.update(name=name, idx=idx, known=known, t=round(dt, 4))
    b = getattr(co, 'chip', None) or {}
    rr = getattr(co, 'rest', None) or {}
    r['chip_lb'] = b.get('lb')
    r['chip_ub'] = b.get('ub')
    r['rest_lb'] = rr.get('lb')
    r['rest_lifts'] = rr.get('lifts')
    r['rest_checks'] = rr.get('checks')
    r['rest_unk'] = rr.get('unk')
    r['rest_t'] = rr.get('t')
    r['rest_certs'] = len(rr.get('certs') or [])
    r['ok'] = bool(r['certified'] and r['opt'] == known
                   and r['audit'] and r['proof']
                   and r['cert_h'] == known - 1)
    return r
