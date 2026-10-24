"""v9.0 GSC-ALC: greedy support-core certification.

Builds on v7.2 QUC.  The new object is a *support core*: for a job i let
S_i be the support of job i in the current feasible LP solution.  If the
LP with all columns {(i,t): t in S_i} deleted is infeasible, then every
feasible schedule has s_i in S_i.  This is valid because a schedule with
s_i outside S_i is a feasible point of the deletion LP.

The support is the *maximal* candidate: if deleting a subset E subset S_i
is infeasible then deleting S_i is infeasible too (monotonicity), so one
probe per job tests all single-job cores inside the support.  Once S_i is
certified, a greedy re-addition loop removes elements while the deletion
LP stays infeasible, yielding an inclusion-minimal core.  The greedy loop
is order independent for minimality.

Root phase:
  * a two-probe prefix of the v7.2 unit scan (catches the 2-unit traps);
  * if no trap, support probes ranked span-first / small support;
  * first certified support core is forced, LP re-solved, then fallback
    to the v7.1 QNC branch.

All probes use the current cut set only (no lazy separation), so each is
one LP.  Found support cores are stored with their Farkas certificates and
replayed by audit_gsc().
"""
import sys
sys.path[:0] = ['exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from quc import QUC, _support_mass
from qnc import Budget, farkas_int
from cert import verify, DENS, _row_meta
import numpy as np
import scipy.sparse as sp
from scipy.optimize import linprog


def farkas_bounded(lp, forbid, U=1000, dens=DENS):
    """Bounded fallback for the Farkas LP.

    Multi-column deletions often make the normalized Farkas LP unbounded
    (HiGHS status 3), although a certificate exists.  Bounding the dual
    variables turns it into a bounded LP whose optimal vertex is still a
    valid integer certificate.  U=1000 is enough on the corpus; the
    caller can retry with larger U if rounding fails.
    """
    A, hi = lp.matrix()
    n_eq, n = lp.n_eq, lp.n
    r = A.shape[0] - n_eq
    present = np.array([cc for cc, key in enumerate(lp.cols)
                        if (key[0], key[-1]) not in forbid], dtype=np.int64)
    if len(present) == 0:
        return None
    B = sp.hstack([A[:n_eq].T, A[n_eq:].T]).tocsr()[present]
    c = np.zeros(n_eq + r)
    c[:n_eq] = 1.0
    c[n_eq:] = hi[n_eq:]
    A_eq = np.zeros((1, n_eq + r))
    A_eq[0, n_eq:] = 1.0
    res = linprog(c, A_ub=-B, b_ub=np.zeros(len(present)),
                  A_eq=A_eq, b_eq=[1.0],
                  bounds=[(-U, U)] * n_eq + [(0, U)] * r,
                  method='highs')
    if res.status != 0 or res.fun >= 0:
        return None
    for D in dens:
        y = np.rint(res.x * D).astype(np.int64)
        s = np.asarray(A.T.dot(y)).ravel()
        bt = int(hi[n:].dot(y[n:])) + int(y[:n].sum())
        if s[present].min() >= 0 and bt < 0:
            meta = _row_meta(lp.base) + [('dom', i, j, t) for (i, j, t) in lp.cuts]
            yb = y[n:]
            return dict(
                kind='packing', scale=D,
                beta=[(m[1], m[2], int(yb[k])) for k, m in enumerate(meta)
                      if m[0] == 'cap' and yb[k]],
                dom=[(m[1], m[2], m[3], int(yb[k])) for k, m in enumerate(meta)
                     if m[0] == 'dom' and yb[k]],
                exp=[(m[1], m[2], int(yb[k])) for k, m in enumerate(meta)
                     if m[0] == 'exp' and yb[k]],
                alpha=[int(v) for v in y[:n]], obj=bt, farkas=res.fun,
                cuts=[meta[k] for k in range(len(meta)) if yb[k]])
    return None


def extract_cert(lp, forbid):
    cert, _ = farkas_int(lp, forbid)
    if cert is not None:
        return cert
    return farkas_bounded(lp, forbid)


def _del_times(lp, i, times):
    b = [(0, 1)] * lp.base.N
    for t in times:
        if lp.elig_aware:
            for k in lp.base.elig[i]:
                key = (i, k, t)
                if key in lp.idx:
                    b[lp.idx[key]] = (0, 0)
        else:
            key = (i, t)
            if key in lp.idx:
                b[lp.idx[key]] = (0, 0)
    return b


class GSC(QUC):
    def __init__(self, inst, h, unit_prefix=2, support_budget=4,
                 minimize=True, min_budget=2, **kw):
        super().__init__(inst, h, **kw)
        self.unit_prefix = unit_prefix
        self.support_budget = support_budget
        self.minimize = minimize
        self.min_budget = min_budget
        self.support_probes = 0
        self.support_cores = []      # (job, times, cert)
        self.support_fail = 0
        self.support_forced = 0

    def _probe_support(self, i, times):
        if self.lp_solves >= self.budget:
            raise Budget
        res = self.lp.solve(_del_times(self.lp, i, times))
        self.lp_solves += 1
        self.support_probes += 1
        if res.status != 2:
            return False, None
        forbid = {(i, t) for t in times}
        cert = extract_cert(self.lp, forbid)
        ok = cert is not None and verify(self.inst, self.h, cert,
                                         forbid=forbid,
                                         elig_aware=self.elig)
        if not ok:
            self.support_fail += 1
            return False, None
        return True, cert

    def _minimize_core(self, i, times, init_cert):
        """Greedy re-addition: drop t while the deletion LP stays infeasible.

        Any order yields an inclusion-minimal core: a dropped element is
        never needed again because feasibility is monotone in the column
        set.  The returned certificate is for the final core.
        """
        E = sorted(times)
        cert = init_cert
        spent = 0
        if not self.minimize or len(E) <= 1:
            return E, cert
        t = 0
        while t < len(E) and spent < self.min_budget:
            cand = E[:t] + E[t + 1:]
            ok, c2 = self._probe_support(i, cand)
            spent += 1
            if ok:
                E = cand
                cert = c2
            else:
                t += 1
        return E, cert

    def _support_scan(self, z):
        S = _support_mass(self.lp, z)
        dom = {i: (min(self._dom[i]), max(self._dom[i])) for i in self._dom}

        def spans(i):
            lo, hi = dom[i]
            return min(S[i]) == lo and max(S[i]) == hi

        jobs = [i for i in range(self.n) if len(S[i]) >= 2]
        jobs.sort(key=lambda i: (0 if spans(i) else 1, len(S[i]),
                                 -round(max(S[i].values()), 6), i))
        probes = 0
        for i in jobs:
            if probes >= self.support_budget:
                return None
            times = sorted(S[i])
            # already forced to exactly this set: probing again is a no-op
            if self.force.get(i) == frozenset(times):
                continue
            ok, cert = self._probe_support(i, times)
            probes += 1
            if not ok:
                continue
            E, cert2 = self._minimize_core(i, times, cert)
            if cert2 is not None:
                cert = cert2
            self.support_cores.append((i, tuple(E), cert))
            self.leaves.append((frozenset((i, t) for t in E),
                                frozenset((i, t) for t in E), cert))
            if self.cert is None:
                self.cert, self.cert_ok = cert, True
            self.force[i] = frozenset(E)
            self.support_forced += 1
            return i
        return None

    def _root_phase(self, max_rounds, topk):
        bounds = [(0, 1)] * self.lp.base.N
        bounds, _ = self._apply_force(bounds)
        i0 = self._empty_job(bounds) if self.use_empty else None
        if i0 is not None:
            self.empty_prunes += 1
            return False, 'empty'
        self.nodes += 1
        res, z = self._solve(bounds, max_rounds, topk)
        if res.status == 2:
            self._learn(self._forbids(bounds))
            return False, 'no'
        if z is None:
            return None, 'roundcap'
        frac = any(1e-7 < v < 1 - 1e-7 for v in z)
        if not frac:
            return True, 'yes'
        self.root_frac = True
        # stage 1: short unit prefix
        old_budget = self.unit_budget
        self.unit_budget = min(self.unit_prefix, old_budget)
        con = self._scan_units(z) if self.unit_scan else None
        self.unit_budget = old_budget
        if con is not None:
            why = 'unit_trap' if con[0] == 'trap' else 'unit_cross'
            return False, why
        if self.units:
            self._apply_units()
            bounds, _ = self._apply_force(bounds)
            self.nodes += 1
            res, z = self._solve(bounds, max_rounds, topk)
            if res.status == 2:
                self._learn(self._forbids(bounds))
                return False, 'no'
            if z is None:
                return None, 'roundcap'
            if not any(1e-7 < v < 1 - 1e-7 for v in z):
                return True, 'yes'
        # stage 2: support cores
        if self.support_budget > 0:
            hit = self._support_scan(z)
            if hit is not None:
                bounds, _ = self._apply_force(bounds)
                self.nodes += 1
                res, z = self._solve(bounds, max_rounds, topk)
                if res.status == 2:
                    self._learn(self._forbids(bounds))
                    return False, 'no'
                if z is None:
                    return None, 'roundcap'
                if not any(1e-7 < v < 1 - 1e-7 for v in z):
                    return True, 'yes'
        return None, 'continue'

    def _stats(self, why):
        st = super()._stats(why)
        st.update(support_probes=self.support_probes,
                  support_cores=[(i, list(E)) for i, E, _ in self.support_cores],
                  support_fail=self.support_fail,
                  support_forced=self.support_forced)
        return st

    def audit_gsc(self):
        if not self.audit_quc():
            return False
        for i, E, cert in self.support_cores:
            if not verify(self.inst, self.h, cert,
                          forbid={(i, t) for t in E},
                          elig_aware=self.elig):
                return False
        return True
