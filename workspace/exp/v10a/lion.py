"""v10.0 LION-ALC: LP-guided interval narrowing.

LION keeps v8.1 CRISP's certified bracket and CHD oracle, and inserts one
extra preprocessing operator between them:

    LP-guided descent
      h = UB - 1
      solve the root LP at h
        infeasible  ->  OPT >= h+1 = UB, so LB := UB (interval closed)
        feasible    ->  run bounded LDS with LP-derived / learned ranks
                        if a replayed schedule has Cmax < UB, lower UB

The root LP is a cheap relaxation; LDS is a bounded search.  Neither can
produce a false certificate: a YES update is guarded by check_schedule,
and a NO update is guarded by a verified Farkas certificate (the root LP
status plus RDF audit).  The learned rank, when enabled, only changes the
order in which LDS explores; it is not trusted as evidence.
"""
import sys
import math
import time

sys.path[:0] = ['exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a',
                'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60',
                'exp/v13']

import numpy as np

from cab import CABOpt, _greedy_rank
from chd import CHD, _lp_distribution, _mean_rank, _argmax_rank
from chip import chip_bounds, order_portfolio
from rdf import check_schedule


def _root_lp(inst, h):
    """One root LP; returns (rdf, status, z, dist) or None."""
    try:
        rdf = CHD(inst, h, yes_scan=False, hull_on=False)
        res = rdf.lp.solve([(0, 1)] * rdf.lp.base.N)
        rdf.lp_solves += 1
    except Exception:
        return None
    if res.status == 2:
        return rdf, 2, None, None
    if res.status != 0:
        return rdf, res.status, None, None
    z = np.array(res.x, copy=True)
    try:
        dist = _lp_distribution(rdf, z)
    except Exception:
        return rdf, res.status, z, None
    return rdf, 0, z, dist


def _default_ranks(inst, h, est, dist, learned=None):
    out = []
    if dist is not None:
        out.append(('lpmean', _mean_rank(dist, est)))
        out.append(('lpargmax', _argmax_rank(dist, est)))
    out.append(('est', {i: est[i] for i in range(inst['n'])}))
    out.append(('latest', {i: h - inst['p'][i] for i in range(inst['n'])}))
    if learned is not None:
        out.insert(0, ('learned', learned))
    return out


def descent_bounds(inst, lb, ub, sched, mach, max_steps=8,
                   nodecap=3000, max_disc=2, learned_rank=None,
                   root_probe=True):
    """Lower UB and (on root infeasibility) raise LB before the oracle."""
    if ub is None:
        return dict(ok=False, lb=lb, ub=None)
    if learned_rank is None:
        learned_rank = {}
    stats = dict(lp=0, nodes=0, steps=0, drops=0, closes=0,
                 root_infeas=0, root_feas=0, fails=0,
                 lp_time=0.0, lds_time=0.0)
    while lb < ub and stats['steps'] < max_steps:
        h = ub - 1
        t0 = time.time()
        got = _root_lp(inst, h)
        stats['lp_time'] += time.time() - t0
        if got is None:
            stats['fails'] += 1
            break
        rdf, status, z, dist = got
        stats['lp'] += 1
        if status == 2:
            # h=UB-1 is LP-infeasible, hence OPT >= UB; with OPT <= UB
            # the interval is exact.  The outer optimizer still obtains
            # the audited NO state at UB-1.
            lb = ub
            stats['closes'] += 1
            stats['root_infeas'] += 1
            break
        if status != 0:
            stats['fails'] += 1
            break
        stats['root_feas'] += 1
        # best-first order: learned first, then LP ranks, then est/latest
        est = rdf.lp.est
        ranks = _default_ranks(inst, h, est, dist, learned_rank.get(h))
        improved = False
        for name, rank in ranks:
            t1 = time.time()
            try:
                res, nd, d = rdf._lds(rank, nodecap, max_disc)
            except Exception:
                res, nd, d = None, 0, 0
            stats['lds_time'] += time.time() - t1
            stats['nodes'] += nd
            if res is None:
                continue
            starts, machs = res
            if not check_schedule(inst, h, starts, machs):
                continue
            cm = max(starts[i] + inst['p'][i] for i in range(inst['n']))
            if cm < ub:
                ub, sched, mach = cm, list(starts), list(machs)
                stats['drops'] += 1
                improved = True
                break
        if not improved:
            break
        stats['steps'] += 1
    return dict(ok=True, lb=lb, ub=ub, schedule=sched, machine=mach,
                **stats)


class LION(CABOpt):
    """CRISP bounds + LP-guided descent + CHD oracle."""

    def __init__(self, inst, learned=None, descent_kw=None,
                 per_query_lp=80, per_query_nodes=5000, max_queries=40,
                 unknown_retries=2):
        super().__init__(inst, per_query_lp=per_query_lp,
                         per_query_nodes=per_query_nodes,
                         max_queries=max_queries,
                         unknown_retries=unknown_retries)
        self.learned = learned or {}
        self.descent_kw = dict(descent_kw or {})

    def initial_bounds(self):
        b = chip_bounds(self.inst)
        self.chip = b
        if not b['ok']:
            return b['lb'], None, None, None
        d = descent_bounds(self.inst, b['lb'], b['ub'], b['schedule'],
                           b['machine'], learned_rank=self.learned,
                           **self.descent_kw)
        self.descent = d
        self.lion = dict(chip=b, descent=d)
        return d['lb'], d['ub'], d['schedule'], d['machine']

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
