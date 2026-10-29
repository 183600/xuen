"""v8.4 LBP-ALC: LP-Bound-Pinned ALC.

CRISP (v8.1) shrinks [LB, UB] by cheap combinatorial rules and then
bisects.  Its residual risk is a wide bracket when the rules miss.

LBP keeps the certified schedule machinery but replaces the lower side
by the LP value function.  Let

    P_h = { z >= 0 : assignment, capacity, and valid SD rows }

be the start-time LP relaxation at horizon h.  P_h is monotone in h, and
every integer schedule with makespan <= h maps into P_h.  Hence

    L* = min { h : P_h feasible }

is a lower bound on OPT.  We compute L* by a binary search on h using a
single *parametric* SD matrix: the horizon is fixed at the incumbent UB,
and a probe at h only zeroes the columns whose start exceeds h-q_i-p_i.
This is the cutting-plane / bundle view of the LP bound: one master LP
is solved at several right-hand sides.

The residual bracket [L*, UB] has width equal to the LP integrality gap
g = OPT - L* (for the integer optimum) plus the UB slack.  The exact
NP-hard CHD oracle is invoked only on this residual:
  * g = 0: no LDS; a fixed-h Farkas certificate at L*-1 closes OPT;
  * g = 1: one CHD query at L*;
  * g > 1: a linear scan for small g, binary search for large g.

Every accepted schedule still passes check_schedule; every NO is a
replayed integer Farkas certificate; audit/proof_complete are inherited.
"""
import sys
import time

import numpy as np
import scipy.sparse as sp
from scipy.optimize import linprog

sys.path[:0] = ['exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a',
                'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60',
                'exp/v13']

from chip import chip_bounds
from cab import CABOpt
from chd import CHD
from sdecc import SDLP
from cert import DENS, _row_meta, integer_certificate, verify
from sdecc import heads_tails


def _elig_aware(inst):
    return any(len(set(inst['elig'][i])) < inst['m']
               for i in range(inst['n']))


class ParametricSD:
    """One full SD matrix at horizon T, solved at several h by bounds."""

    def __init__(self, inst, T):
        self.inst = inst
        self.T = T
        self.elig = _elig_aware(inst)
        self.lp = SDLP(inst, T, use_dom=True, elig_aware=self.elig)
        self.n = inst['n']
        self.p = inst['p']
        self.q = self.lp.q
        self.cols = self.lp.cols
        self.N = self.lp.N
        self.solves = 0

    def bounds_h(self, h):
        b = [(0, 1)] * self.N
        for cc, key in enumerate(self.cols):
            i, t = key[0], key[-1]
            if t > h - self.q[i] - self.p[i]:
                b[cc] = (0, 0)
        return b

    def solve_h(self, h):
        res = self.lp.solve(self.bounds_h(h))
        self.solves += 1
        return res


def lp_threshold(inst, lo, hi, T=None):
    """Smallest h in [lo,hi] whose parametric SD LP is feasible.

    The invariant P_hi feasible is supplied by the incumbent schedule at
    hi.  A feasible probe is only a relaxation statement, so it may
    underestimate L*; an infeasible probe is a valid NO for every h at or
    below the probe, but we only use it to move lo.  The returned value is
    therefore always <= OPT.
    """
    if T is None:
        T = hi
    ps = ParametricSD(inst, T)
    solves = 0
    unknown = 0
    last_res = None
    last_h = None
    while lo < hi:
        mid = (lo + hi) // 2
        res = ps.solve_h(mid)
        solves += 1
        if res.status == 0:
            hi = mid
            last_res = res
            last_h = mid
        elif res.status == 2:
            lo = mid + 1
        else:
            unknown += 1
            break
    return dict(ok=(unknown == 0), lb=lo, ub=hi, solves=solves,
                unknown=unknown, N=ps.N, rows=ps.lp.A.shape[0],
                T=T, param=ps, last_res=last_res, last_h=last_h)


def cp_cert(inst, h):
    """Critical-path certificate: est_i + p_i + q_i > h."""
    est, q = heads_tails(inst, 0, [0] * inst['n'])
    for i in range(inst['n']):
        if est[i] + inst['p'][i] + q[i] > h:
            return dict(kind='cp', job=i, est=est[i], p=inst['p'][i],
                        q=q[i], h=h, scale=1, beta=[], dom=[], exp=[],
                        alpha=[], obj=-1, cuts=[])
    return None


def farkas_bounds(lp, h, bounds, dens=DENS):
    """Farkas certificate for the h-restricted parametric SDLP.

    The parametric matrix is built at T = UB.  Restricting to h means
    deleting columns whose start is too late and rows whose horizon is
    at least h; the dual below is the Farkas system of that restricted
    primal.  It reuses the already-built matrix, so no second SDLP is
    constructed for the NO proof.
    """
    A, hi = (lp.A, lp.hi) if hasattr(lp, 'A') else lp.matrix()
    n_eq, n = lp.n_eq, lp.n
    meta = _row_meta(lp)
    if hasattr(lp, 'cuts'):
        meta += [('dom', i, j, t) for (i, j, t) in lp.cuts]
    keep = list(range(n_eq))
    sel = []
    for k, m in enumerate(meta):
        ok = (m[0] == 'exp'
              or (m[0] == 'cap' and m[2] < h)
              or (m[0] == 'dom' and m[3] < h - lp.q[m[1]] - lp.p[m[1]]))
        if ok:
            keep.append(n_eq + k)
            sel.append(m)
    keep = np.array(keep, dtype=np.int64)
    Ah = A[keep].tocsr()
    hih = hi[keep]
    r = Ah.shape[0] - n_eq
    present = np.array([cc for cc in range(len(bounds))
                        if bounds[cc] != (0, 0)], dtype=np.int64)
    if len(present) == 0:
        return None
    B = Ah[:, present].T.tocsr()
    b = np.concatenate([np.ones(n_eq), hih[n:]])
    A_ub = sp.vstack([-B, b.reshape(1, -1)]).tocsr()
    b_ub = np.concatenate([np.zeros(len(present)), [-1.0]])
    res = linprog(np.zeros(n_eq + r), A_ub=A_ub, b_ub=b_ub,
                  bounds=[(None, None)] * n_eq + [(0, None)] * r,
                  method='highs')
    if res.status != 0:
        return None
    for D in dens:
        y = np.rint(res.x * D).astype(np.int64)
        ATy = Ah.T.dot(y)
        bt = int(hih[n:].dot(y[n:])) + int(y[:n].sum())
        if ATy[present].min() >= 0 and bt < 0:
            yb = y[n:]
            return dict(
                kind='packing', scale=D,
                beta=[(m[1], m[2], int(yb[k])) for k, m in enumerate(sel)
                      if m[0] == 'cap' and yb[k]],
                dom=[(m[1], m[2], m[3], int(yb[k])) for k, m in enumerate(sel)
                     if m[0] == 'dom' and yb[k]],
                exp=[(m[1], m[2], int(yb[k])) for k, m in enumerate(sel)
                     if m[0] == 'exp' and yb[k]],
                alpha=[int(v) for v in y[:n]], obj=bt, cuts=[])
    return None


def lp_schedule(ps, inst, h, res=None):
    """Read a verified integral schedule from a feasible parametric LP.

    Returns (starts, machines) or None.  The LP solution is integral if
    every task has one column at 1.0 (within 1e-7).  For aggregate
    capacity (full eligibility) the machines are assigned greedily; the
    result must still pass check_schedule.
    """
    if res is None:
        res = ps.solve_h(h)
    if res.status != 0:
        return None
    z = res.x
    n, m, p = inst['n'], inst['m'], inst['p']
    starts = [None] * n
    machs = [None] * n
    for cc, key in enumerate(ps.cols):
        if z[cc] > 1 - 1e-7:
            i, t = key[0], key[-1]
            if starts[i] is not None:
                return None
            starts[i] = t
            if ps.elig:
                machs[i] = key[1]
    if any(x is None for x in starts):
        return None
    if not ps.elig:
        busy = [[] for _ in range(m)]
        for i in sorted(range(n), key=lambda i: (starts[i], i)):
            t = starts[i]
            for k in inst['elig'][i]:
                if all(t + p[i] <= a or t >= b for (a, b) in busy[k]):
                    machs[i] = k
                    busy[k].append((t, t + p[i]))
                    break
            if machs[i] is None:
                return None
    from rdf import check_schedule
    if check_schedule(inst, h, starts, machs):
        return starts, machs
    return None


class PinProof:
    """A fixed-h Farkas certificate produced without the CHD search."""

    def __init__(self, inst, h, cert):
        self.inst = inst
        self.h = h
        self.cert = cert

    def audit_rdf(self):
        return bool(self.cert is not None
                    and verify(self.inst, self.h, self.cert))

    def proof_complete(self):
        return bool(self.cert is not None)


class LBP(CABOpt):
    """CRISP bounds with the lower side pinned by the LP value function."""

    def __init__(self, inst, scan_cap=4, **kw):
        super().__init__(inst, **kw)
        self.scan_cap = scan_cap
        self.pin = None
        self.chip = None
        self.pin_lp = 0
        self.cert_lp = 0
        self.lp_bound_bad = 0
        self.lp_primal = 0
        self.cert_cp = 0
        self.cert_fb = 0
        self.cert_full = 0
        self.final_lp = 0

    def initial_bounds(self):
        b = chip_bounds(self.inst)
        self.chip = b
        if not b.get('ok') or b.get('ub') is None:
            return b.get('lb'), None, None, None
        pin = lp_threshold(self.inst, b['lb'], b['ub'], T=b['ub'])
        self.pin = pin
        self.pin_lp = pin['solves']
        lb = b['lb']
        if pin.get('ok') and pin.get('lb') is not None:
            lb = max(lb, pin['lb'])
        return lb, b['ub'], b['schedule'], b['machine']

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

    def _lp_no_proof(self, h):
        """NO proof at h from the parametric LP, with safe fallbacks."""
        self.cert_lp += 1
        cert = cp_cert(self.inst, h)
        if cert is not None:
            self.cert_cp += 1
        else:
            p = self.pin or {}
            ps = p.get('param')
            if ps is not None:
                cert = farkas_bounds(ps.lp, h, ps.bounds_h(h))
                if cert is not None:
                    self.cert_fb += 1
            if cert is None:
                cert = integer_certificate(self.inst, h, use_dom=True,
                                           elig_aware=_elig_aware(self.inst))
                if cert is not None:
                    self.cert_full += 1
        if cert is not None and verify(self.inst, h, cert):
            return PinProof(self.inst, h, cert)
        return None

    def _record_yes(self, rdf, h):
        n = self.inst['n']
        p = self.inst['p']
        cmax = max(rdf.schedule[i] + p[i] for i in range(n))
        if cmax < h:
            self.lp_bound_bad += 1
            return False
        self.opt = cmax
        self.schedule = list(rdf.schedule)
        self.machine = list(rdf.machine)
        return True

    def _gap_proof(self, h):
        """NO proof at h: previous CHD state, else fixed-h LP, else CHD."""
        if h in self.no_states:
            return self.no_states[h]
        proof = self._lp_no_proof(h)
        if proof is not None:
            return proof
        v, st, rdf = self._decide(h)
        self.queries += 1
        self._absorb(st)
        self._record(h, v, st)
        if v is False:
            self.no_states[h] = rdf
            return rdf
        return None

    def _gap_scan(self, lb, ub):
        h = lb
        while h < ub and self.queries < self.max_queries:
            v, st, rdf = self._decide(h)
            self.queries += 1
            self._absorb(st)
            self._record(h, v, st)
            if v is True:
                if not self._record_yes(rdf, h):
                    return
                self.lb = h
                proof = self._gap_proof(h - 1)
                self.lb_proof = proof
                self.certified = bool(proof is not None
                                      and proof.audit_rdf())
                return
            if v is False:
                self.lb = h + 1
                self.no_states[h] = rdf
                self.lb_proof = rdf
                h += 1
                continue
            self.unknown += 1
            v2, st2, rdf2 = self._decide(h)
            self.queries += 1
            self._absorb(st2)
            self._record(h, v2, st2)
            if v2 is True:
                if not self._record_yes(rdf2, h):
                    return
                self.lb = h
                proof = self._gap_proof(h - 1)
                self.lb_proof = proof
                self.certified = bool(proof is not None
                                      and proof.audit_rdf())
                return
            if v2 is False:
                self.lb = h + 1
                self.no_states[h] = rdf2
                self.lb_proof = rdf2
                h += 1
                continue
            return
        if self.lb == self.opt and self.lb_proof is not None:
            self.certified = True

    def _binary_search(self, lb, ub):
        while lb < self.opt and self.queries < self.max_queries:
            h = (lb + self.opt) // 2
            v, st, rdf = self._decide(h)
            self.queries += 1
            self._absorb(st)
            self._record(h, v, st)
            if v is True:
                self._record_yes(rdf, h)
            elif v is False:
                lb = max(lb, h + 1)
                self.no_states[h] = rdf
                self.lb_proof = rdf
            else:
                self.unknown += 1
                self._recover_unknown(h)
                lb = max(lb, self.lb)
        self.lb = lb
        if self.lb == self.opt:
            if (self.opt - 1) not in self.no_states:
                proof = self._lp_no_proof(self.opt - 1)
                if proof is None:
                    v, st, rdf = self._decide(self.opt - 1)
                    self.queries += 1
                    self._absorb(st)
                    self._record(self.opt - 1, v, st)
                    if v is False:
                        self.no_states[self.opt - 1] = rdf
                        proof = rdf
                self.lb_proof = proof
            else:
                self.lb_proof = self.no_states[self.opt - 1]
            self.certified = bool(self.lb_proof is not None
                                  and self.lb_proof.audit_rdf())

    def _lp_schedule_at(self, h):
        p = self.pin or {}
        ps = p.get('param')
        if ps is None:
            return None
        res = p.get('last_res') if p.get('last_h') == h else None
        if res is None:
            res = ps.solve_h(h)
            self.pin_lp += 1
        got = lp_schedule(ps, self.inst, h, res=res)
        if got is not None:
            self.lp_primal += 1
        return got

    def optimize(self):
        lb, ub, starts, machs = self.initial_bounds()
        self.lb0, self.ub0 = lb, ub
        self.lb = lb
        if ub is None:
            return self._result()
        self.schedule, self.machine, self.opt = starts, machs, ub
        if lb == ub:
            proof = self._lp_no_proof(ub - 1)
            if proof is None:
                v, st, rdf = self._decide(ub - 1)
                self.queries += 1
                self._absorb(st)
                self._record(ub - 1, v, st)
                if v is False:
                    self.no_states[ub - 1] = rdf
                    proof = rdf
            if proof is not None:
                self.lb_proof = proof
                self.certified = True
        elif ub - lb <= self.scan_cap:
            got = self._lp_schedule_at(lb)
            if got is not None:
                self.opt = lb
                self.schedule, self.machine = got
                self.lb = lb
                proof = self._gap_proof(lb - 1)
                self.lb_proof = proof
                self.certified = bool(proof is not None
                                      and proof.audit_rdf())
            else:
                self._gap_scan(lb, ub)
        else:
            self._binary_search(lb, ub)
        self.lp_total += self.pin_lp + self.cert_lp
        self.final_lp = self.lp_total
        return self._result()


class LBPNoEnergy(LBP):
    """Ablation: no energy/window lift before the LP pin."""

    def initial_bounds(self):
        from chip import base_bounds, order_portfolio
        from cab import _greedy_rank
        from rdf import check_schedule
        lb0, ub, starts, machs, est, q = base_bounds(self.inst)
        if ub is None:
            return lb0, None, None, None
        sched, mach = starts, machs
        for _, rank in order_portfolio(self.inst, est, q, ub):
            g = _greedy_rank(self.inst, rank)
            if g is not None and g[2] < ub \
                    and check_schedule(self.inst, g[2], g[0], g[1]):
                ub, sched, mach = g[2], g[0], g[1]
        self.chip = dict(ok=True, lb0=lb0, ub0=ub, lb=lb0, ub=ub,
                         schedule=sched, machine=mach, lifts=0, drops=0,
                         cert_bad=0)
        pin = lp_threshold(self.inst, lb0, ub, T=ub)
        self.pin = pin
        self.pin_lp = pin['solves']
        lb = lb0
        if pin.get('ok') and pin.get('lb') is not None:
            lb = max(lb, pin['lb'])
        return lb, ub, sched, mach


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
    r['lifts'] = b.get('lifts')
    r['drops'] = b.get('drops')
    r['cert_bad'] = b.get('cert_bad')
    r['pin_lb'] = p.get('lb')
    r['pin_solves'] = p.get('solves')
    r['pin_N'] = p.get('N')
    r['pin_rows'] = p.get('rows')
    r['pin_lp'] = getattr(co, 'pin_lp', 0)
    r['cert_lp'] = getattr(co, 'cert_lp', 0)
    r['lp_bound_bad'] = getattr(co, 'lp_bound_bad', 0)
    r['lp_primal'] = getattr(co, 'lp_primal', 0)
    r['cert_cp'] = getattr(co, 'cert_cp', 0)
    r['cert_fb'] = getattr(co, 'cert_fb', 0)
    r['cert_full'] = getattr(co, 'cert_full', 0)
    r['gap_lp'] = (None if p.get('lb') is None or p.get('ub') is None
                   else p['ub'] - p['lb'])
    r['gap_opt'] = (None if p.get('lb') is None else known - p['lb'])
    r['ok'] = bool(r['certified'] and r['opt'] == known
                   and r['audit'] and r['proof']
                   and r['cert_h'] == known - 1)
    return r
