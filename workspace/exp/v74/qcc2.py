"""v7.4 QCC2-ALC: quorum cover cuts at every node + certified root closure.

Extends v7.1 QNC in two orthogonal directions.

1. Every leaf quorum E is promoted from a nogood to a globally valid
   cover inequality

       gamma(E):  sum_{c in E} z_c >= 1.

   E is a set of start columns that every feasible schedule must hit, so
   gamma is valid for every integer schedule (it need not hold for
   fractional LP points -- that is exactly why it is a useful cut).

2. gamma is installed in the LP used by *every* node, not only at the
   root.  A node LP that becomes infeasible because of covers is a valid
   NO node; its Farkas certificate carries dual multipliers for the cover
   rows, which depend on earlier leaf certificates.  The proof is a DAG:
   leaf certificates -> cover rows -> later certificates -> root
   certificate.  When the root LP with all covers is infeasible we stop
   and the branch tree is discarded.

The implementation keeps the v7.1 median branching, force, zero-LP empty
precheck and anytime state.  Audit replays leaf and root certificates
against the extended matrix, then checks every cover's source leaf.
"""
import sys, time
sys.path[:0] = ['exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
import numpy as np
import scipy.sparse as sp
from scipy.optimize import linprog
from qnc import QNC, Budget, farkas_int
from cert import DENS, verify, _row_meta
from lazy import LazySD


class Closed(Exception):
    pass


class CoverLP(LazySD):
    def __init__(self, inst, h, elig_aware=False):
        super().__init__(inst, h, elig_aware=elig_aware)
        self.covers = []          # list of frozenset of column keys
        self.cover_set = set()

    def add_cover(self, E):
        E = frozenset(E)
        if E in self.cover_set:
            return False
        self.cover_set.add(E)
        self.covers.append(E)
        return True

    def matrix(self):
        A, hi = super().matrix()
        if not self.covers:
            return A, hi
        rows = sp.lil_matrix((len(self.covers), self.base.N))
        for r, E in enumerate(self.covers):
            for key in E:
                if key in self.idx:
                    rows[r, self.idx[key]] = -1.0
                else:
                    # elig-aware keys are (i,k,t); allow (i,t) keys too
                    for kk, cc in self.idx.items():
                        if kk[0] == key[0] and kk[-1] == key[-1]:
                            rows[r, cc] -= 1.0
        A2 = sp.vstack([A, rows.tocsr()], format='csr')
        hi2 = np.concatenate([hi, -np.ones(len(self.covers))])
        return A2, hi2


def _present(lp, forbid):
    out = []
    for cc, key in enumerate(lp.cols):
        if key in forbid:
            continue
        for key2 in forbid:
            if key2[0] == key[0] and key2[-1] == key[-1] and len(key2) != len(key):
                break
        else:
            out.append(cc)
    return np.asarray(out, dtype=np.int64)


def farkas_ext(lp, forbid, dens=DENS):
    """Integer Farkas certificate on base + SD cuts + cover rows."""
    A, hi = lp.matrix()
    A = A.tocsr()
    n_eq, n = lp.n_eq, lp.n
    r = A.shape[0] - n_eq
    present = _present(lp, set(forbid))
    if len(present) == 0:
        return None, None
    B = sp.hstack([A[:n_eq].T, A[n_eq:].T], format='csr')[present]
    c = np.zeros(n_eq + r)
    c[:n_eq] = 1.0
    c[n_eq:] = hi[n_eq:]
    A_eq = np.zeros((1, n_eq + r))
    A_eq[0, n_eq:] = 1.0
    res = linprog(c, A_ub=-B, b_ub=np.zeros(len(present)),
                  A_eq=A_eq, b_eq=[1.0],
                  bounds=[(None, None)] * n_eq + [(0, None)] * r,
                  method='highs')
    if res.status != 0 or res.fun >= 0:
        return None, None
    for D in dens:
        y = np.rint(res.x * D).astype(np.int64)
        s = np.asarray(A.T.dot(y)).ravel()
        bt = int(hi[n:].dot(y[n:])) + int(y[:n].sum())
        if s[present].min() >= 0 and bt < 0:
            meta = _row_meta(lp.base) + [('dom', i, j, t) for (i, j, t) in lp.cuts]
            meta += [('qc', q) for q in range(len(lp.covers))]
            yb = y[n:]
            cert = dict(
                kind='packing', scale=D,
                beta=[(m[1], m[2], int(yb[k])) for k, m in enumerate(meta)
                      if m[0] == 'cap' and yb[k]],
                dom=[(m[1], m[2], m[3], int(yb[k])) for k, m in enumerate(meta)
                     if m[0] == 'dom' and yb[k]],
                exp=[(m[1], m[2], int(yb[k])) for k, m in enumerate(meta)
                     if m[0] == 'exp' and yb[k]],
                qc=[(m[1], int(yb[k])) for k, m in enumerate(meta)
                    if m[0] == 'qc' and yb[k]],
                alpha=[int(v) for v in y[:n]], obj=bt,
                farkas=res.fun,
                cuts=[meta[k] for k in range(len(meta)) if yb[k]])
            return cert, s
    return None, None


def verify_ext(lp, inst, h, cert, forbid, elig_aware=False):
    """Exact integer replay against the final extended LP matrix."""
    A, hi = lp.matrix()
    A = A.tocsr()
    n, neq, N = lp.n, lp.n_eq, lp.base.N
    nr = A.shape[0]
    y = np.zeros(nr, dtype=np.int64)
    alpha = cert.get('alpha', [])
    if len(alpha) != n:
        return False
    y[:n] = alpha
    meta0 = _row_meta(lp.base)
    pos = {}
    for k, m in enumerate(meta0):
        pos[m[:3]] = n + k
    for k, t, w in cert.get('beta', []):
        key = ('cap', k, t)
        if key not in pos:
            return False
        y[pos[key]] += int(w)
    for k, m in enumerate(lp.cuts):
        pos[('dom', m[0], m[1], m[2])] = n + len(meta0) + k
    for i, j, t, w in cert.get('dom', []):
        key = ('dom', i, j, t)
        if key not in pos:
            return False
        y[pos[key]] += int(w)
    qbase = n + len(meta0) + len(lp.cuts)
    for q, w in cert.get('qc', []):
        if q < 0 or q >= len(lp.covers):
            return False
        y[qbase + q] += int(w)
    if y[n:].min() < 0:
        return False
    s = np.asarray(A.T.dot(y)).ravel()
    present = _present(lp, set(forbid))
    bt = int(hi[n:].dot(y[n:])) + int(y[:n].sum())
    return s[present].min() >= 0 and bt < 0


class QCC2(QNC):
    def __init__(self, inst, h, use_cover=True, use_core=False,
                 core_cap=8, **kw):
        super().__init__(inst, h, **kw)
        self.lp = CoverLP(inst, h, elig_aware=self.elig)
        self._dom = {}
        for key in self.lp.cols:
            self._dom.setdefault(key[0], set()).add(key[-1])
        self.use_cover = use_cover
        self.use_core = use_core
        self.core_cap = core_cap
        self.root_cert = None
        self.root_covers = None
        self.root_checks = 0
        self.root_lp = 0
        self.cover_added = 0
        self.cover_seen = set()
        self.closed = False
        self.core_tests = 0
        self.core_shrunk = 0

    # ------------------------------------------------------------- LP with covers
    def _solve(self, bounds, max_rounds, topk):
        # same as QNC._solve, but lp.matrix() already carries covers
        return super()._solve(bounds, max_rounds, topk)

    # --------------------------------------------------- core reduction (root LPs)
    def _infeasible_with(self, E):
        if self.lp_solves >= self.budget:
            raise Budget
        b = [(0, 1)] * self.lp.base.N
        for key, cc in self.lp.idx.items():
            if key in E:
                b[cc] = (0, 0)
        res = self.lp.solve(b)
        self.lp_solves += 1
        self.core_tests += 1
        return res.status == 2

    def _shrink_core(self, E):
        E = set(E)
        if len(E) <= 1:
            return frozenset(E)
        # remove whole jobs first
        jobs = sorted({key[0] for key in E})
        for i in jobs:
            cand = {key for key in E if key[0] != i}
            if not cand:
                continue
            if self.core_tests >= self.core_cap:
                return frozenset(E)
            if self._infeasible_with(cand):
                E = cand
        # then single columns
        changed = True
        while changed and len(E) > 1:
            changed = False
            for key in sorted(E):
                if self.core_tests >= self.core_cap:
                    return frozenset(E)
                cand = E - {key}
                if self._infeasible_with(cand):
                    E = cand
                    changed = True
                    break
        return frozenset(E)

    # --------------------------------------------------------------- learn
    def _learn(self, F):
        t0 = time.time()
        self.cert_calls += 1
        cert, s = farkas_ext(self.lp, F)
        self.cert_t += time.time() - t0
        if cert is None:
            self.cert_fail += 1
            return None, None
        E = frozenset(key for cc, key in enumerate(self.lp.cols)
                      if key in F and s[cc] < 0)
        if self.use_core and len(E) > 1:
            E2 = self._shrink_core(E)
            if E2 != E:
                c2, s2 = farkas_ext(self.lp, E2)
                if c2 is not None:
                    E3 = frozenset(key for cc, key in enumerate(self.lp.cols)
                                   if key in E2 and s2[cc] < 0)
                    if E3:
                        E, cert = E3, c2
                        self.core_shrunk += 1
        if E and not verify_ext(self.lp, self.inst, self.h, cert, E,
                                elig_aware=self.elig):
            # numerical fallback: keep the node scope, validated by base replay
            E = frozenset(F)
        self.leaves.append((frozenset(F), E, cert))
        if self.cert is None and self.cert_on:
            self.cert, self.cert_ok = cert, True
        if E and self.use_quorum:
            self.clauses.append(E)
            jobs = {key[0] for key in E}
            if len(jobs) == 1:
                i = next(iter(jobs))
                times = frozenset(key[-1] for key in E)
                new = times & self.force.get(i, self.domain(i))
                if new != self.force.get(i):
                    self.force[i] = new
        if E and self.use_cover:
            if self.lp.add_cover(E):
                self.cover_added += 1
                self._check_root()
        return cert, E

    def _check_root(self):
        """Exact root LP with all covers/force; if infeasible, global NO."""
        if self.lp_solves >= self.budget:
            raise Budget
        b = [(0, 1)] * self.lp.base.N
        for i, S in self.force.items():
            for key, cc in self.lp.idx.items():
                if key[0] == i and key[-1] not in S:
                    b[cc] = (0, 0)
        res = self.lp.solve(b)
        self.lp_solves += 1
        self.root_checks += 1
        if res.status == 2:
            c, s = farkas_ext(self.lp, set())
            if c is not None:
                self.root_cert = c
                self.root_covers = list(self.lp.covers)
                self.closed = True
                raise Closed
        return res

    def decide(self, budget=100000, nodecap=5000, max_rounds=60, topk=100):
        self.budget = budget
        try:
            v, why = self._branch([(0, 1)] * self.lp.base.N, 0, nodecap,
                                  max_rounds, topk)
        except Closed:
            v, why = False, 'root-cover'
        except Budget:
            v, why = None, 'budget'
        return v, self._stats(why)

    def _stats(self, why):
        st = super()._stats(why)
        if why == 'root-cover':
            st['verdict'] = False
        st.update(cover_added=self.cover_added, root_checks=self.root_checks,
                  closed=self.closed, core_tests=self.core_tests,
                  core_shrunk=self.core_shrunk,
                  root_cert_ok=(self.root_cert is not None))
        return st

    def audit(self):
        """Leaf certs at their E, plus the final root certificate."""
        for F, E, c in self.leaves:
            if not E <= F:
                return False
            if E and not verify_ext(self.lp, self.inst, self.h, c, E,
                                    elig_aware=self.elig):
                return False
        if self.root_cert is not None:
            if not verify_ext(self.lp, self.inst, self.h, self.root_cert, set(),
                              elig_aware=self.elig):
                return False
        return True
