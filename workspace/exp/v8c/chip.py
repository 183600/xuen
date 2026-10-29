"""v8.1 CRISP-ALC: competitive-ratio interval shrinking preprocessing.

CRISP keeps the v8.0 BRC-ALC fixed-h oracle and adds an outer layer:

  * a certified bracket [LB, UB] with LB <= OPT <= UB;
  * LB lifting by replayable window/energy NO certificates;
  * UB dropping by a portfolio of greedy list schedules;
  * binary search over the reduced bracket with the CHD oracle.

The high-dimensional LP projection box is available as an ordering oracle
but is off by default: on this corpus it is too wide to prune.
"""
import sys
import math
import time
import json

sys.path[:0] = ['exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

import numpy as np
from scipy.optimize import linprog

from cab import CABOpt, _greedy_rank
from chd import CHD
from scale import energy_cert, windows, verify_prep
from po import heads_tails
from rdf import check_schedule
from lazy import LazySD


def base_bounds(inst):
    """Critical path + eligibility load + first greedy schedule."""
    n, m, elig = inst['n'], inst['m'], inst['elig']
    est, q = heads_tails(inst, 0, [0] * n)
    lb = max(est[i] + inst['p'][i] + q[i] for i in range(n))
    for mask in range(1, 1 << m):
        jobs = [i for i in range(n)
                if all((mask >> k) & 1 for k in elig[i])]
        load = sum(inst['p'][i] for i in jobs)
        cnt = bin(mask).count('1')
        lb = max(lb, (load + cnt - 1) // cnt)
    g = _greedy_rank(inst, {i: est[i] + i * 1e-9 for i in range(n)})
    if g is None:
        return lb, None, None, None, est, q
    return lb, g[2], g[0], g[1], est, q


def order_portfolio(inst, est, q, ub):
    """Deterministic greedy orders used to lower the upper bound."""
    n = inst['n']
    latest = [ub - q[i] - inst['p'][i] for i in range(n)]
    return [
        ('est', {i: est[i] + i * 1e-9 for i in range(n)}),
        ('latest', {i: latest[i] + i * 1e-9 for i in range(n)}),
        ('tail', {i: -q[i] + i * 1e-9 for i in range(n)}),
        ('mixed', {i: est[i] - 0.5 * q[i] + i * 1e-9
                   for i in range(n)}),
    ]


def hull_projection(inst, h):
    """Coordinate projection of the LP polytope: [lo_i, hi_i].

    This is a sound outer box but it is deliberately not installed as a
    hard domain: the box can be much wider than the integer feasible set.
    """
    n = inst['n']
    elig = any(len(set(inst['elig'][i])) < inst['m'] for i in range(n))
    lp = LazySD(inst, h, elig_aware=elig)
    A, hi = lp.matrix()
    lo, up, fail = {}, {}, 0
    for i in range(n):
        c = np.zeros(lp.base.N)
        for cc, key in enumerate(lp.cols):
            if key[0] == i:
                c[cc] = key[-1]
        r1 = linprog(c, A_ub=A, b_ub=hi, A_eq=A[:lp.n_eq],
                     b_eq=np.ones(lp.n), bounds=[(0, 1)] * lp.base.N,
                     method='highs')
        r2 = linprog(-c, A_ub=A, b_ub=hi, A_eq=A[:lp.n_eq],
                     b_eq=np.ones(lp.n), bounds=[(0, 1)] * lp.base.N,
                     method='highs')
        if r1.status != 0 or r2.status != 0:
            fail += 1
            lo[i] = lp.est[i]
            up[i] = lp.est[i] + inst['p'][i]
        else:
            lo[i] = float(r1.fun)
            up[i] = -float(r2.fun)
    return lo, up, fail, 2 * n


def chip_bounds(inst, energy_max_subsets=64, energy_max_intervals=20000,
                verify=True):
    """Certified bracket before any exact oracle call."""
    lb0, ub0, starts, machs, est, q = base_bounds(inst)
    if ub0 is None:
        return dict(ok=False, lb0=lb0, ub0=None)
    lb, ub = lb0, ub0
    sched, mach = starts, machs
    drops = 0
    for name, rank in order_portfolio(inst, est, q, ub):
        g = _greedy_rank(inst, rank)
        if g is not None and g[2] < ub \
                and check_schedule(inst, g[2], g[0], g[1]):
            ub, sched, mach = g[2], g[0], g[1]
            drops += 1
    lifts = 0
    certs = []
    cert_bad = 0
    while lb < ub:
        cert = energy_cert(inst, lb, energy_max_subsets,
                           energy_max_intervals)
        if cert is None:
            ee, ll, _ = windows(inst, lb)
            if not any(ee[i] > ll[i] for i in range(inst['n'])):
                break
            cert = dict(kind='window')
        if verify:
            if cert['kind'] == 'energy':
                good = verify_prep(inst, lb, cert)
            else:
                ee, ll, _ = windows(inst, lb)
                good = any(ee[i] > ll[i] for i in range(inst['n']))
            if not good:
                cert_bad += 1
                break
        certs.append((lb, cert))
        lifts += 1
        lb += 1
    return dict(ok=True, lb0=lb0, ub0=ub0, lb=lb, ub=ub,
                schedule=sched, machine=mach, lifts=lifts, drops=drops,
                certs=certs, cert_bad=cert_bad,
                ratio0=ub0 / lb0 if lb0 > 0 else None,
                ratio=ub / lb if lb > 0 else None)


class CRISPBounds(CABOpt):
    """Ablation: CRISP bounds with the original CAB oracle."""

    def initial_bounds(self):
        b = chip_bounds(self.inst)
        self.chip = b
        return b['lb'], b['ub'], b['schedule'], b['machine']


class CRISP(CABOpt):
    """CRISP: reduced bracket + deterministic CHD oracle."""

    def initial_bounds(self):
        b = chip_bounds(self.inst)
        self.chip = b
        return b['lb'], b['ub'], b['schedule'], b['machine']

    def _decide(self, h):
        rdf = CHD(self.inst, h, yes_scan=True, cheap_disc=2,
                  hull_disc=4, hull_on=True)
        try:
            v, st = rdf.decide(budget=self.per_query_lp,
                               nodecap=self.per_query_nodes)
        except Exception:
            v, st = None, rdf._stats('exception')
        self.last_oracle = rdf
        return v, st, rdf


def simulate_queries(lb, ub, opt):
    """Binary-search depth with an exact oracle, excluding final replay."""
    q = 0
    while lb < ub:
        h = (lb + ub) // 2
        q += 1
        if opt <= h:
            ub = h
        else:
            lb = h + 1
    return q


def run(cls, inst, known, name, idx):
    t0 = time.time()
    co = cls(inst)
    r = co.optimize()
    dt = time.time() - t0
    r.update(name=name, idx=idx, known=known, t=round(dt, 4))
    b = getattr(co, 'chip', None) or {}
    r['lifts'] = b.get('lifts')
    r['drops'] = b.get('drops')
    r['cert_bad'] = b.get('cert_bad')
    r['ok'] = bool(r['certified'] and r['opt'] == known
                   and r['audit'] and r['proof']
                   and r['cert_h'] == known - 1)
    return r


def corpus_rows(rows):
    return dict(
        n=len(rows),
        cert=sum(bool(r['certified']) for r in rows),
        ok=sum(bool(r['ok']) for r in rows),
        q=sum(r['queries'] for r in rows),
        lp=sum(r['lp'] for r in rows),
        yn=sum(r['yes_nodes'] for r in rows),
        mc=sum(r['mc_evals'] for r in rows),
        t=round(sum(r['t'] for r in rows), 3),
        lifts=sum((r.get('lifts') or 0) for r in rows),
        drops=sum((r.get('drops') or 0) for r in rows),
        cert_bad=sum((r.get('cert_bad') or 0) for r in rows),
        qdist={k: sum(1 for r in rows if r['queries'] == k)
               for k in range(0, 6)},
    )


def _load(f):
    import pickle
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple)
            else (x['inst'], x['opt']) for x in d]


FILES = {'holdout': 'exp/v20/holdout_cases50.pkl',
         'synth': 'exp/v28/synth2_45.pkl',
         'large_a': 'exp/v14/large_a.pkl',
         'large_b': 'exp/v14/large_b.pkl',
         'large_het': 'exp/v14/large_het.pkl',
         'hard3': 'exp/v13/hard3.pkl',
         'deep': 'exp/v18/deep.pkl'}


def base_corpus():
    return [(name, idx, inst, opt)
            for name, f in FILES.items()
            for idx, (inst, opt) in enumerate(_load(f))]


def pert_corpus():
    import pickle
    d = pickle.load(open('exp/v71/perturb60.pkl', 'rb'))
    return [(name, k, inst, opt)
            for (name, k, inst, opt, _, _) in d]


def stress_corpus():
    import pickle
    d = pickle.load(open('exp/v81/h5h47_branch.pkl', 'rb'))
    return [(r['idx'], r['h'] + 1, r['inst']) for r in d]
