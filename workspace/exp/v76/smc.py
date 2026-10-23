"""v7.3 SMC-ALC: support-mining closure.

v7.2 QUC probes single atoms (i,t): if deleting (i,t) makes the node LP
infeasible, then every feasible schedule has s_i=t.  That rule is sound
but blind to a *set* of atoms that only conflict jointly.

This round transforms the probe.  At a fractional node, take a job i and
delete its whole current support S_i(z).  If the deletion LP is
infeasible, extract the essential scope E of its integer Farkas
certificate.  The quorum lemma gives the globally valid clause

    OR_{(j,t) in E} (s_j = t),        LP(C, E) infeasible.

When E lives on the single job i, the clause is a *domain force*

    every feasible schedule has s_i in E_i,

so the global domain of i can be shrunk to E_i.  This strictly generalises
both v7.2 singleton forces and v7.1's leaf force: one support-deletion LP
can return a singleton core, a two-point core, or a proper subset of the
support.  The search then re-solves the node with the shrunk domain and
repeats (a force-recursion / closure).  If the closure reaches an
infeasible LP, the ordinary QNC leaf certificate closes the node; if no
force is found, the algorithm falls back to the v7.1 median split.

The essential scope computation is the same negative-column-slack replay
used by v7.1, but with the objective-normalised dual extraction of QLS
(b^T y = -1), which is bounded even when the dual cone is unbounded.

Proof objects:
  * a force certificate Phi_E with verify(Phi_E, forbid=E);
  * a leaf certificate Phi_F with verify(Phi_F, forbid=E_leaf) (QNC);
  * a conflict is two force certificates for the same job with disjoint
    allowed sets (an empty domain).
The final NO verdict is either a QNC leaf (globally valid on its own) or
a force conflict; audit replays both, so the search transformations never
enter the trusted base.
"""
import sys

sys.path[:0] = ['exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

import numpy as np
import scipy.sparse as sp
from scipy.optimize import linprog

from qnc import QNC, Budget
from cert import DENS, verify, _row_meta


def farkas_obj(lp, forbid, dens=DENS):
    """Integer Farkas certificate normalised by b^T y = -1."""
    A, hi = lp.matrix()
    n_eq, N, n = lp.n_eq, lp.base.N, lp.n
    r = A.shape[0] - n_eq
    present = np.array([cc for cc, key in enumerate(lp.cols)
                        if (key[0], key[-1]) not in forbid], dtype=np.int64)
    if len(present) == 0:
        return None, None
    B = sp.hstack([A[:n_eq].T, A[n_eq:].T]).tocsr()[present]
    b = np.concatenate([np.ones(n_eq), hi[n_eq:]])
    res = linprog(np.zeros(n_eq + r), A_ub=-B, b_ub=np.zeros(len(present)),
                  A_eq=[b], b_eq=[-1.0],
                  bounds=[(None, None)] * n_eq + [(0, None)] * r,
                  method='highs')
    if res.status != 0:
        return None, None
    for D in dens:
        y = np.rint(res.x * D).astype(np.int64)
        s = np.asarray(A.T.dot(y)).ravel()
        bt = int(b.dot(y))
        if s[present].min() >= 0 and bt < 0:
            meta = _row_meta(lp.base) + [('dom', i, j, t)
                                         for (i, j, t) in lp.cuts]
            yb = y[n:]
            cert = dict(kind='packing', scale=D,
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
                        farkas=res.fun,
                        cuts=[meta[k] for k in range(len(meta)) if yb[k]])
            return cert, s
    return None, None


def _support(lp, z, tol=1e-7):
    S = {}
    for cc, key in enumerate(lp.cols):
        v = float(z[cc])
        if v > tol:
            d = S.setdefault(key[0], {})
            d[key[-1]] = d.get(key[-1], 0.0) + v
    return S


class SMC(QNC):
    def __init__(self, inst, h, mine=True, order='slack', mine_budget=24,
                 node_budget=3, use_clause=True, **kw):
        super().__init__(inst, h, **kw)
        self.mine = mine
        self.order = order
        self.mine_budget = mine_budget
        self.node_budget = node_budget
        self.use_clause = use_clause
        self.mine_probes = 0
        self.mine_hits = 0
        self.mine_fail = 0
        self.force_events = []     # (job, allowed, E, cert)
        self.force_depths = []     # parallel to force_events
        self.force_log = {}        # job -> [(allowed, E, cert)]
        self.conflict = None       # (job, old_allowed, old_E, old_cert,
                                   #  new_allowed, new_E, new_cert)
        self.mine_clauses = 0
        self.root_frac = False

    # ------------------------------------------------------------- helpers
    def _live(self, i, bounds):
        return {key[-1] for cc, key in enumerate(self.lp.cols)
                if key[0] == i and bounds[cc] != (0, 0)}

    def _job_order(self, S, bounds, z):
        rows = []
        for i, mass in S.items():
            supp = set(mass)
            live = self._live(i, bounds)
            slack = len(live) - len(supp)
            span = (min(supp) == min(live) and max(supp) == max(live))
            mm = max(mass.values())
            if self.order == 'slack':
                key = (-slack, len(supp), -mm, i)
            elif self.order == 'support':
                key = (len(supp), -slack, -mm, i)
            elif self.order == 'ratio':
                key = (len(supp) / max(1, len(live)), -slack, -mm, i)
            elif self.order == 'span':
                key = (0 if span else 1, -slack, len(supp), -mm, i)
            elif self.order == 'mass':
                key = (-mm, -slack, len(supp), i)
            elif self.order == '2dom':
                key = (len(supp) != 2, -len(live), len(supp), -mm, i)
            elif self.order == '2span':
                key = (len(supp) != 2, 0 if span else 1,
                       -len(live), -mm, i)
            elif self.order == '2frac':
                key = (0 if len(supp) == 2 else
                       1 if len(supp) == 3 else 2,
                       -len(live), -mm, i)
            elif self.order == 'quc':
                key = (0 if span else 1, len(supp), -mm, i)
            else:
                key = (i,)
            rows.append((key, i, supp))
        rows.sort()
        return [(i, supp) for _, i, supp in rows]

    def _probe_support(self, i, S_i, bounds):
        """Delete all live support columns of job i; return (E, cert)."""
        if self.mine_probes >= self.mine_budget:
            raise Budget
        b2 = list(bounds)
        for cc, key in enumerate(self.lp.cols):
            if key[0] == i and key[-1] in S_i and b2[cc] != (0, 0):
                b2[cc] = (0, 0)
        res = self.lp.solve(b2)
        self.lp_solves += 1
        self.mine_probes += 1
        if res.status != 2:
            return None
        F = self._forbids(b2)
        cert, slack = farkas_obj(self.lp, F)
        if cert is None:
            self.mine_fail += 1
            return None
        E = frozenset((key[0], key[-1])
                      for cc, key in enumerate(self.lp.cols)
                      if (key[0], key[-1]) in F and slack[cc] < 0)
        if not E:
            self.mine_fail += 1
            return None
        if not verify(self.inst, self.h, cert, forbid=E,
                      elig_aware=self.elig):
            self.mine_fail += 1
            return None
        return E, cert

    def _apply_mined_force(self, i, E_i, E, cert):
        """Install a single-job quorum as a global domain force."""
        cur = self.force.get(i, self.domain(i))
        new = frozenset(E_i) & cur
        if new == cur:
            return 'none'
        self.mine_hits += 1
        if not new:
            old = self.force_log.get(i, [])
            old_allowed = frozenset(cur)
            old_E, old_cert = (old[-1][1], old[-1][2]) if old else (None, None)
            self.conflict = (i, old_allowed, old_E, old_cert,
                             frozenset(new), E, cert)
            self.force[i] = new
            return 'conflict'
        self.force[i] = new
        self.force_events.append((i, new, E, cert))
        self.force_depths.append(getattr(self, '_cur_depth', 0))
        self.force_log.setdefault(i, []).append((new, E, cert))
        return 'force'

    def _mine_pass(self, bounds, z):
        """One mining pass: return ('force'|'conflict'|'clause'|None)."""
        S = _support(self.lp, z)
        acted = False
        for i, S_i in self._job_order(S, bounds, z):
            if self.mine_probes >= self.mine_budget:
                break
            if self.mine_probes - getattr(self, '_node_start', 0) >= \
                    self.node_budget:
                break
            got = self._probe_support(i, S_i, bounds)
            if got is None:
                continue
            E, cert = got
            jobs = {j for (j, t) in E}
            if len(jobs) == 1:
                j = next(iter(jobs))
                E_j = frozenset(t for (jj, t) in E if jj == j)
                kind = self._apply_mined_force(j, E_j, E, cert)
                if kind == 'conflict':
                    return 'conflict'
                if kind == 'force':
                    return 'force'
            elif self.use_clause:
                if E not in self.clauses:
                    self.clauses.append(E)
                    self.mine_clauses += 1
                acted = True
        return 'clause' if acted else None

    # -------------------------------------------------------------- search
    def _search(self, base, depth):
        self._node_start = self.mine_probes
        loop = 0
        while True:
            bounds, _ = self._apply_force(base)
            i0 = self._empty_job(bounds) if self.use_empty else None
            if i0 is not None:
                self.empty_prunes += 1
                return False, 'empty'
            F = self._forbids(bounds)
            for E in self.clauses:
                if E <= F:
                    self.prunes += 1
                    return False, 'clause'
            if loop == 0:
                self.nodes += 1
                if self.nodes > self.nodecap:
                    raise Budget
            res, z = self._solve(bounds, 60, 100)
            if res.status == 2:
                self._learn(F)
                return False, 'no'
            if z is None:
                return None, 'roundcap'
            frac = [(abs(z[cc] - 0.5), cc, key[0], key[-1])
                    for cc, key in enumerate(self.lp.cols)
                    if 1e-7 < z[cc] < 1 - 1e-7]
            if not frac:
                return True, 'yes'
            if depth == 0:
                self.root_frac = True
            if self.mine and self.mine_probes < self.mine_budget:
                kind = self._mine_pass(bounds, z)
                if kind == 'conflict':
                    return False, 'mine-conflict'
                if kind == 'force':
                    loop += 1
                    continue
                if kind == 'clause':
                    pass  # clauses prune descendants; current LP is unchanged
            # ---- v7.1 median fallback
            frac.sort()
            _, cc, i, t = frac[0]
            times = sorted(self.domain(i))
            s = 0.0
            mid = t
            for tt in times:
                if self.elig:
                    s += sum(z[self.lp.idx[(i, k, tt)]]
                             for k in self.lp.base.elig[i]
                             if (i, k, tt) in self.lp.idx)
                else:
                    s += z[self.lp.idx[(i, tt)]]
                if s >= 0.5:
                    mid = tt
                    break
            if mid >= times[-1]:
                mid = times[-1] - 1
            lo = list(bounds)
            hi2 = list(bounds)
            for tt in times:
                if self.elig:
                    for k in self.lp.base.elig[i]:
                        if (i, k, tt) not in self.lp.idx:
                            continue
                        c2 = self.lp.idx[(i, k, tt)]
                        if tt > mid:
                            lo[c2] = (0, 0)
                        else:
                            hi2[c2] = (0, 0)
                else:
                    c2 = self.lp.idx[(i, tt)]
                    if tt > mid:
                        lo[c2] = (0, 0)
                    else:
                        hi2[c2] = (0, 0)
            a, why = self._search(lo, depth + 1)
            if a is not False:
                return a, why
            return self._search(hi2, depth + 1)

    def decide(self, budget=100000, nodecap=5000, max_rounds=60, topk=100):
        self.budget = budget
        self.nodecap = nodecap
        try:
            v, why = self._search([(0, 1)] * self.lp.base.N, 0)
        except Budget:
            v, why = None, 'budget'
        return v, self._stats(why)

    def _stats(self, why):
        st = super()._stats(why)
        st.update(mine_probes=self.mine_probes, mine_hits=self.mine_hits,
                  mine_fail=self.mine_fail,
                  mine_clauses=self.mine_clauses,
                  mine_conflict=self.conflict is not None,
                  mine_budget=self.mine_budget,
                  root_frac=self.root_frac,
                  force_events=[(i, sorted(a)) for i, a, _, _ in
                                self.force_events])
        if self.conflict is not None:
            st['verdict'] = False
        return st

    def audit_smc(self):
        if not self.audit():
            return False
        for i, allowed, E, cert in self.force_events:
            if not verify(self.inst, self.h, cert, forbid=E,
                          elig_aware=self.elig):
                return False
            if not allowed:
                return False
        if self.conflict is not None:
            (i, old_allowed, old_E, old_cert,
             new_allowed, new_E, new_cert) = self.conflict
            if new_allowed:
                return False
            if not verify(self.inst, self.h, new_cert, forbid=new_E,
                          elig_aware=self.elig):
                return False
            if old_cert is not None:
                if old_E is None:
                    return False
                if not verify(self.inst, self.h, old_cert, forbid=old_E,
                              elig_aware=self.elig):
                    return False
                if old_allowed & new_allowed:
                    return False
            else:
                # the mined clause is disjoint from the original domain
                if new_E is None:
                    return False
                if {t for (j, t) in new_E if j == i} & self.domain(i):
                    return False
        return True
