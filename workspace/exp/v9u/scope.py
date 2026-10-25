"""v9.2 SCOPE-ALC: streaming column-restricted rounding on top of PACT.

SCOPE keeps PACT's bracket, total trace, complete certificate search and
STAB store.  It adds a one-sided YES filter at the root of every probe:

    solve the root SDLP once;
    if it is integral, decode and check the schedule;
    if it is fractional, stream a small portfolio of column restrictions
    (support, threshold, top-k per job), solve each restricted LP, and
    accept only a schedule that passes check_schedule.

Every accepted schedule is a genuine YES.  A failed restriction proves
nothing, so the filter is sound regardless of how coarse the column set
is.  The filter never changes a NO verdict: if the root LP is infeasible
we hand the same root LP to PACT's complete search.

The overlap/DAG layer is deliberately not assumed: the root LP object is
shared with the complete search, and the restricted LPs reuse the same
row matrix.  The design is a streaming algorithm in the sense that the
column sets are generated in one pass and the restricted LPs are solved
and discarded; memory is O(nT) for the shared matrix plus O(n) per
schedule.
"""
import sys
import time

sys.path[:0] = ['exp/v9u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

import numpy as np
from scipy.optimize import linprog

from sage import SAGE, _elig_aware
from sdecc import SDLP
from po import heads_tails
from rdf import check_schedule
from pact import (PACT, TotalTrace, pact_decide, _integral_schedule,
                  _assign_machines)


def _restricted_solve(lp, cols):
    cols = sorted(set(cols))
    if not cols:
        return None
    A = lp.A.tocsr()[:, cols]
    n_eq = lp.n_eq
    try:
        r = linprog(np.zeros(len(cols)),
                    A_ub=A[n_eq:], b_ub=lp.hi[n_eq:],
                    A_eq=A[:n_eq], b_eq=np.ones(lp.n),
                    bounds=(0, 1), method='highs')
    except Exception:
        return None
    return r


def _decode(lp, inst, h, cols, x):
    z = np.zeros(lp.N)
    z[cols] = x
    return _integral_schedule(inst, lp, z, _elig_aware(inst))


def lp_round_probe(inst, h, root_lp=None, root_res=None, budget=3,
                   order=('support', 'thr02', 'top2')):
    """Try a stream of column restrictions; return a checked YES or None.

    Returns dict(verdict, schedule, machine, lp, lp_obj, root_res,
    attempts, sets, t).  `verdict` is True only when a schedule passed
    check_schedule.  `lp_obj`/`root_res` are handed to PACT so the root
    LP is not solved twice.
    """
    t0 = time.time()
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    elig = _elig_aware(inst)
    lp = root_lp
    if lp is None:
        lp = SDLP(inst, h, est, q, use_dom=True, elig_aware=elig)
    res = root_res if root_res is not None else lp.solve()
    out = dict(verdict=None, schedule=None, machine=None, lp=1,
               lp_obj=lp, root_res=res, attempts=0, sets=[], t=0.0)
    if res.status != 0:
        out['t'] = round(time.time() - t0, 5)
        return out
    z = res.x
    frac = [c for c in range(lp.N) if 1e-7 < z[c] < 1 - 1e-7]
    if not frac:
        got = _integral_schedule(inst, lp, z, elig)
        if got is not None:
            out.update(verdict=True, schedule=got[0], machine=got[1])
        out['t'] = round(time.time() - t0, 5)
        return out
    # Candidate column sets, generated in one pass over the LP columns.
    support = [c for c in range(lp.N) if z[c] > 1e-7]
    thr = [c for c in range(lp.N) if z[c] > 0.2]
    top2 = []
    by_job = {}
    for c, key in enumerate(lp.cols):
        by_job.setdefault(key[0], []).append(c)
    for i in range(n):
        cs = sorted(by_job.get(i, []), key=lambda c: -z[c])[:2]
        top2.extend(cs)
    all_sets = {'support': support, 'thr02': thr, 'top2': top2}
    candidates = [(name, all_sets[name]) for name in order if name in all_sets]
    for name, cols in candidates:
        if out['attempts'] >= budget:
            break
        # every job must keep at least one column
        have = {lp.cols[c][0] for c in cols}
        if len(have) < n:
            extra = []
            for i in range(n):
                if i not in have:
                    cs = by_job.get(i, [])
                    if cs:
                        extra.append(max(cs, key=lambda c: z[c]))
            cols = list(cols) + extra
        out['attempts'] += 1
        out['lp'] += 1
        rr = _restricted_solve(lp, cols)
        out['sets'].append((name, len(set(cols)), None if rr is None else rr.status))
        if rr is None or rr.status != 0:
            continue
        got = _decode(lp, inst, h, sorted(set(cols)), rr.x)
        if got is not None:
            out.update(verdict=True, schedule=got[0], machine=got[1],
                       hit=name)
            break
    out['t'] = round(time.time() - t0, 5)
    return out


class SCOPE(PACT):
    """PACT with a streaming LP-rounding filter and optional DAG search."""

    def __init__(self, inst, scope_mode='complete', scope_budget=3,
                 scope_gate=None, scope_order=('support', 'thr02', 'top2'),
                 scope_dag=False, scope_spacecap=512, **kw):
        super().__init__(inst, **kw)
        self.scope_mode = scope_mode
        self.scope_budget = scope_budget
        self.scope_gate = scope_gate
        self.scope_order = scope_order
        self.scope_dag = scope_dag
        self.scope_spacecap = scope_spacecap
        self.round_lp = 0
        self.round_yes = 0
        self.round_restricted = 0
        self.round_calls = 0
        self.round_attempts = 0
        self.round_sets = []
        self.scope_steps = []

    def _probe(self, h):
        if self.scope_mode == 'complete':
            if self.scope_gate == 'closing' and h < self.opt - 1:
                return super()._probe(h)
            if self.scope_gate == 'ub2' and h < self.opt - 2:
                return super()._probe(h)
            if self.scope_gate == 'ub3' and h < self.opt - 3:
                return super()._probe(h)
            rf = lp_round_probe(self.inst, h, budget=self.scope_budget,
                                order=self.scope_order)
            self.round_calls += 1
            self.round_lp += rf['lp']
            self.round_attempts += rf['attempts']
            self.round_sets.append(rf['sets'])
            if rf['verdict'] is True:
                s, m = rf['schedule'], rf['machine']
                cmax = max(s[i] + self.inst['p'][i]
                           for i in range(self.inst['n']))
                if cmax < self.opt and check_schedule(self.inst, cmax, s, m):
                    self.round_yes += 1
                    if rf.get('hit'):
                        self.round_restricted += 1
                    self.steps.append(dict(h=h, v=True, schedule=s,
                                           machine=m, cmax=cmax,
                                           engine='round',
                                           hit=rf.get('hit')))
                    return True, (s, m, cmax)
            r = pact_decide(self.inst, h, depthcap=None, nodecap=None,
                            root_lp=rf['lp_obj'], root_res=rf['root_res'])
            self.pact_lp += r['lp_solves']
            self.pact_cert_lp += r.get('cert_lp', 0)
            self.pact_nodes += r['nodes']
            if r['verdict'] is False:
                self.pact_no += 1
                self.stats['pact_no'] += 1
                self._record_proof(r['proof'])
                self.steps.append(dict(h=h, v=False, proof=r['proof'],
                                       engine='complete'))
                return False, r['proof']
            if r['verdict'] is True:
                self.pact_yes += 1
                self.stats['pact_yes'] += 1
                s, m = r['schedule'], r['machine']
                cmax = max(s[i] + self.inst['p'][i]
                           for i in range(self.inst['n']))
                self.steps.append(dict(h=h, v=True, schedule=s,
                                       machine=m, cmax=cmax,
                                       engine='complete'))
                return True, (s, m, cmax)
        return super()._probe(h)

    def _result(self):
        r = super()._result()
        r.update(round_lp=self.round_lp, round_yes=self.round_yes,
                 round_calls=self.round_calls,
                 round_attempts=self.round_attempts,
                 round_restricted=self.round_restricted,
                 round_sets=self.round_sets)
        return r


def run_scope(inst, known, name, idx, **kw):
    t0 = time.time()
    co = SCOPE(inst, **kw)
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
                   and r['audit'] and r['proof'] and r['total_audit']
                   and r['cert_h'] == known - 1)
    return r
