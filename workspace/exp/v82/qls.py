"""QLS-ALC prototype: quorum local search by support deletion.

Builds on v7.1 QNC.  At a feasible fractional node z, delete the support
of z and re-solve.  If the deletion LP is infeasible, its integer Farkas
certificate yields an essential scope E (a quorum).  When E lives on one
job, split the node into the |E| cases s_i=t; each is a smaller LP.  The
quorum certificate plus the child certificates is a complete NO proof.
"""
import sys, time
sys.path[:0] = ['exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
import numpy as np
import scipy.sparse as sp
from scipy.optimize import linprog
from qnc import QNC, Budget
from cert import DENS, verify, _row_meta


def farkas_obj(lp, forbid, dens=DENS):
    """Integer Farkas certificate normalized by b^T y = -1.

    v7.1's farkas_int normalizes sum(ineq duals)=1; when the dual cone is
    unbounded this returns HiGHS status 3 and the certificate is lost.
    Normalizing the objective instead always gives a bounded feasible LP.
    """
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
            meta = _row_meta(lp.base) + [('dom', i, j, t) for (i, j, t) in lp.cuts]
            yb = y[n:]
            cert = dict(kind='packing', scale=D,
                        beta=[(m[1], m[2], int(yb[k])) for k, m in enumerate(meta)
                              if m[0] == 'cap' and yb[k]],
                        dom=[(m[1], m[2], m[3], int(yb[k])) for k, m in enumerate(meta)
                             if m[0] == 'dom' and yb[k]],
                        exp=[(m[1], m[2], int(yb[k])) for k, m in enumerate(meta)
                             if m[0] == 'exp' and yb[k]],
                        alpha=[int(v) for v in y[:n]], obj=bt, farkas=res.fun,
                        cuts=[meta[k] for k in range(len(meta)) if yb[k]])
            return cert, s
    return None, None


class QLS(QNC):
    def __init__(self, inst, h, mine=True, split=True, support_min=True,
                 fallback=True, max_depth=20, **kw):
        super().__init__(inst, h, **kw)
        self.mine = mine
        self.do_split = split
        self.support_min = support_min
        self.fallback = fallback
        self.max_depth = max_depth
        self.splits = 0
        self.mines = 0
        self.mine_fail = 0
        self.split_lits = 0
        self.proofs = []          # (F, E, cert, verify)
        self.split_nodes = []     # (parent_E, job, times)

    def _solve_any(self, bounds):
        res, z = self._solve(bounds, 60, 100)
        return res, z

    def _mine(self, bounds, z):
        """Delete support(z); return (E, cert) if the result is infeasible."""
        supp = [c for c in range(self.lp.base.N) if z[c] > 1e-7]
        if not supp:
            return None, None
        b2 = list(bounds)
        for c in supp:
            b2[c] = (0, 0)
        res, z2 = self._solve_any(b2)
        self.mines += 1
        if res.status != 2:
            self.mine_fail += 1
            return None, None
        F = self._forbids(b2)
        cert, s = farkas_obj(self.lp, F)
        if cert is None:
            self.mine_fail += 1
            return None, None
        E = frozenset(key for cc, key in enumerate(self.lp.cols)
                      if key in F and s[cc] < 0)
        ok = verify(self.inst, self.h, cert, forbid=E,
                    elig_aware=self.elig)
        self.proofs.append((frozenset(F), E, cert, ok))
        if not ok:
            return None, None
        return E, cert

    def _median_child(self, bounds, z, frac_key):
        i, t = frac_key
        times = sorted(self.domain(i))
        ssum = 0.0
        mid = t
        for tt in times:
            if self.elig:
                ssum += sum(z[self.lp.idx[(i, k, tt)]]
                            for k in self.lp.base.elig[i]
                            if (i, k, tt) in self.lp.idx)
            else:
                ssum += z[self.lp.idx[(i, tt)]]
            if ssum >= 0.5:
                mid = tt
                break
        if mid >= times[-1]:
            mid = times[-1] - 1
        lo = list(bounds); hi2 = list(bounds)
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
        return lo, hi2, i, mid

    def _search(self, bounds, depth):
        bounds, _ = self._apply_force(bounds)
        if self._empty_job(bounds) is not None:
            self.empty_prunes += 1
            return False, 'empty'
        F = self._forbids(bounds)
        for E in self.clauses:
            if E <= F:
                self.prunes += 1
                return False, 'clause'
        self.nodes += 1
        if self.nodes > self.nodecap:
            raise Budget
        if depth > self.max_depth:
            return None, 'depth'
        res, z = self._solve_any(bounds)
        if res.status == 2:
            cert, E = self._analyse(F)
            if cert is not None:
                self.leaves.append((frozenset(F), E, cert))
                if E:
                    self.clauses.append(E)
                    jobs = {i for (i, t) in E}
                    if len(jobs) == 1:
                        i = next(iter(jobs))
                        times = frozenset(t for (_, t) in E)
                        new = times & self.force.get(i, self.domain(i))
                        if new != self.force.get(i):
                            self.force[i] = new
            return False, 'no'
        if res.status != 0 or z is None:
            return None, 'other'
        frac = [(abs(z[c] - 0.5), c, key[0], key[-1])
                for c, key in enumerate(self.lp.cols)
                if 1e-7 < z[c] < 1 - 1e-7]
        if not frac:
            return True, 'yes'
        # ---- quorum mining by support deletion
        if self.mine:
            E, cert = self._mine(bounds, z)
            if E is not None:
                jobs = sorted({i for (i, t) in E})
                if self.do_split and len(jobs) == 1:
                    i = jobs[0]
                    times = sorted(t for (_, t) in E)
                    self.splits += 1
                    self.split_lits += len(times)
                    self.split_nodes.append((E, i, tuple(times)))
                    any_unknown = False
                    for t in times:
                        b2 = list(bounds)
                        for c, key in enumerate(self.lp.cols):
                            if key[0] == i and key[-1] != t:
                                b2[c] = (0, 0)
                        v, why = self._search(b2, depth + 1)
                        if v is True:
                            return True, 'yes'
                        if v is None:
                            any_unknown = True
                    return (None, 'unknown') if any_unknown else (False, 'quorum-split')
                if not E:
                    return False, 'empty-quorum'
                # multi-job: fall through to median
        # ---- fallback median branch
        if not self.fallback:
            return None, 'nomine'
        frac.sort()
        _, c, i, t = frac[0]
        lo, hi2, i, mid = self._median_child(bounds, z, (i, t))
        a, why = self._search(lo, depth + 1)
        if a is not True:
            b, why2 = self._search(hi2, depth + 1)
            if b is not True:
                return (None, 'unknown') if (a is None or b is None) else (False, 'no')
            return True, 'yes'
        return True, 'yes'

    def decide(self, budget=100000, nodecap=5000, max_rounds=60, topk=100):
        self.budget = budget
        self.nodecap = nodecap
        try:
            v, why = self._search([(0, 1)] * self.lp.base.N, 0)
        except Budget:
            v, why = None, 'budget'
        return v, self._stats(why)
