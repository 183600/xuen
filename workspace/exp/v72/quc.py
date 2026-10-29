"""v7.2 QUC-ALC: quorum unit traps found at the root by support scanning.

QNC v7.1 learns quorum clauses only at infeasible leaves.  This module
adds a *root* phase.  If the root LP is feasible but fractional, let S_i
be the support of job i's start variable in the current LP solution.
The support lemma says that every singleton quorum {(i,t)} (i.e. every
t that is forced, LP({(i,t)}) infeasible) must satisfy t in S_i.
Therefore two distinct forced starts of the same job -- already a
contradiction for integer schedules -- can be found by probing only the
support, with no branching.

Each probe is one LP with a single start deleted.  A successful probe
yields an integer Farkas certificate verified at forbid={(i,t)}.  Two
such certificates on the same job are a two-leaf refutation; a pair on
different jobs is also a refutation if it violates a precedence edge or
a time-capacity bound (unit consensus).  If the scan finds nothing, the
algorithm falls back to the v7.1 QNC search.
"""
import sys
sys.path[:0] = ['exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
import numpy as np
from qnc import QNC, Budget, farkas_int
from cert import verify


def _support_mass(lp, z, tol=1e-7):
    """Support of every job's start variable in a (possibly elig-aware) LP."""
    S = {i: {} for i in range(lp.n)}
    if lp.elig_aware:
        for (i, k, t), c in lp.idx.items():
            v = float(z[c])
            if v > tol:
                S[i][t] = S[i].get(t, 0.0) + v
    else:
        for (i, t), c in lp.idx.items():
            v = float(z[c])
            if v > tol:
                S[i][t] = v
    return S


def _del_bounds(lp, i, t):
    b = [(0, 1)] * lp.base.N
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


class QUC(QNC):
    def __init__(self, inst, h, use_quorum=True, use_empty=True,
                 unit_budget=6, unit_scan=True):
        super().__init__(inst, h, use_quorum=use_quorum,
                         use_empty=use_empty)
        self.unit_budget = unit_budget
        self.unit_scan = unit_scan
        self.units = []          # (job, start, cert)
        self.unit_certs = {}     # (job, start) -> cert
        self.trap = None         # (job, t, u)
        self.cross = None        # (i, t, j, u, constraint)
        self.unit_probes = 0
        self.unit_forced = 0
        self.unit_fail = 0
        self.root_frac = False

    # ---------- unit probes ----------
    def _probe_unit(self, i, t):
        if self.lp_solves >= self.budget:
            raise Budget
        b = _del_bounds(self.lp, i, t)
        res = self.lp.solve(b)
        self.lp_solves += 1
        self.unit_probes += 1
        if res.status != 2:
            return False, None
        cert, _ = farkas_int(self.lp, {(i, t)})
        ok = cert is not None and verify(self.inst, self.h, cert,
                                         forbid={(i, t)},
                                         elig_aware=self.elig)
        if not ok:
            self.unit_fail += 1
            return False, None
        self.unit_forced += 1
        return True, cert

    def _unit_conflict(self):
        """Check certified singleton units against hard constraints."""
        U = {}
        for i, t, _ in self.units:
            if i in U and U[i] != t:
                return ('trap', i, U[i], t)
            U[i] = t
        for i, t in U.items():
            for j in self.inst['succ'][i]:
                if j in U and U[j] < t + self.inst['p'][i]:
                    return ('prec', i, t, j, U[j])
        for i, t in U.items():
            for tau in range(t, min(t + self.inst['p'][i], self.h + 1)):
                c = sum(1 for j, u in U.items()
                        if u <= tau < u + self.inst['p'][j])
                if c > self.inst['m']:
                    return ('cap', tau, c, self.inst['m'])
        return None

    def _scan_units(self, z):
        S = _support_mass(self.lp, z)
        dom = {i: (min(self._dom[i]), max(self._dom[i])) for i in self._dom}
        def spans(i):
            lo, hi = dom[i]
            return min(S[i]) == lo and max(S[i]) == hi
        jobs = [i for i in range(self.n) if len(S[i]) >= 2]
        # Boundary-spanning supports first: they are the fractional traps
        # seen in the hard instances.  The ordering affects only the probe
        # budget, never correctness.
        jobs.sort(key=lambda i: (0 if spans(i) else 1,
                                 len(S[i]),
                                 -round(max(S[i].values()), 6), i))
        probes = 0
        for i in jobs:
            ts = sorted(S[i])
            if spans(i) and len(ts) > 1:
                order = [ts[0], ts[-1]] + ts[1:-1]
            else:
                order = sorted(ts, key=lambda t: (-S[i][t], t))
            for t in order:
                if probes >= self.unit_budget:
                    return None
                if (i, t) in self.unit_certs:
                    continue
                ok, cert = self._probe_unit(i, t)
                probes += 1
                if not ok:
                    continue
                self.unit_certs[(i, t)] = cert
                self.units.append((i, t, cert))
                self.leaves.append((frozenset({(i, t)}),
                                    frozenset({(i, t)}), cert))
                if self.cert is None:
                    self.cert, self.cert_ok = cert, True
                con = self._unit_conflict()
                if con is not None:
                    if con[0] == 'trap':
                        self.trap = (con[1], con[2], con[3])
                    else:
                        self.cross = con
                    return con
            if probes >= self.unit_budget:
                return None
        return None

    def _apply_units(self):
        for i, t, _ in self.units:
            self.force[i] = frozenset({t})

    # ---------- root phase ----------
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
        if self.unit_scan:
            con = self._scan_units(z)
            if con is not None:
                why = 'unit_trap' if con[0] == 'trap' else 'unit_cross'
                return False, why
            self._apply_units()
        return None, 'continue'

    def decide(self, budget=100000, nodecap=5000, max_rounds=60, topk=100):
        self.budget = budget
        try:
            v, why = self._root_phase(max_rounds, topk)
            if v is None and why != 'continue':
                pass
            elif v is None:
                v, why = self._branch([(0, 1)] * self.lp.base.N, 0,
                                      nodecap, max_rounds, topk)
        except Budget:
            v, why = None, 'budget'
        return v, self._stats(why)

    def _stats(self, why):
        st = super()._stats(why)
        st.update(unit_probes=self.unit_probes,
                  unit_forced=self.unit_forced,
                  unit_fail=self.unit_fail,
                  unit_budget=self.unit_budget,
                  root_frac=self.root_frac,
                  trap=self.trap, cross=self.cross,
                  units=[(i, t) for i, t, _ in self.units],
                  unit_certs=len(self.unit_certs))
        return st

    def audit_quc(self):
        if not self.audit():
            return False
        for i, t, c in self.units:
            if not verify(self.inst, self.h, c, forbid={(i, t)},
                          elig_aware=self.elig):
                return False
        if self.trap is not None:
            i, t, u = self.trap
            if t == u:
                return False
            if (i, t) not in self.unit_certs or (i, u) not in self.unit_certs:
                return False
        if self.cross is not None:
            if self.cross[0] == 'cap':
                _, tau, c, m = self.cross
                U = {i: t for (i, t) in self.unit_certs}
                cnt = sum(1 for j, u in U.items()
                          if u <= tau < u + self.inst['p'][j])
                if cnt != c or cnt <= m:
                    return False
            else:
                i, t, j, u = self.cross[:4]
                if (i, t) not in self.unit_certs or (j, u) not in self.unit_certs:
                    return False
                if j not in self.inst['succ'][i] or not (u < t + self.inst['p'][i]):
                    return False
        return True
