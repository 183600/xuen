"""v7.4 QMC-ALC: quorum minimal cores + certified cover convergence.

Starting from v7.1 QNC-ALC, a leaf certificate with forbid set F yields an
essential scope E = {c in F : column slack < 0}.  v7.1 uses E as a nogood
(clause) and, for a single job, as a domain force.  Two weaknesses remain:

  (W1) E depends on the arbitrary dual vertex returned by the Farkas LP;
       it is minimal *for that y*, not a minimal deletion set.
  (W2) a clause only fires when a node's forbid set contains all of E, a
       shape that threshold branching almost never produces.

This module fixes both.

Cover convergence (W2).  Every clause is promoted to a globally valid
cover inequality

    gamma(E):   sum_{c in E} z_c >= 1.

It is valid for every integer schedule (the clause says the schedule uses
at least one column of E) but not necessarily for fractional LP points,
so it is a genuine cut.  gamma(E) is installed at the root.  After each
new cut the root is re-solved; if the root LP becomes infeasible, the
instance is NO and the proof is the chain of clause certificates plus one
root Farkas certificate.  The branch tree is then only a search heuristic
and is absent from the proof.

Minimal core selection (W1).  If the root is still feasible after adding
gamma(E), solve the selection LP

    min  sum_{c in E} t_c
    s.t. (A^T y)_c + t_c >= 0   (c in E)
         (A^T y)_c      >= 0   (c not in E)
         b^T y <= -eps,  sum_{ineq} y = 1,  t >= 0

over the Farkas dual face.  Its negative-slack set E' is a smaller
candidate core.  An exact integer Farkas replay on E' returns E'' subset
E'; gamma(E'') is stronger than gamma(E) and is added as a second cut.
The shrink is lazy: it runs only when the cheaper original cut did not
already close the root, so easy instances never pay for it.

Audit.  Each cover keeps its source integer certificate.  Leaves are
replayed at E; the root certificate is replayed against the extended
matrix (base + SD cuts + cover rows).  This is a proof DAG, not a tree.
"""
import sys, time
sys.path[:0] = ['exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
import numpy as np
import scipy.sparse as sp
from scipy.optimize import linprog
from qnc import QNC, Budget, farkas_int
from cert import DENS, verify, _row_meta


class Closed(Exception):
    pass


def cols_of(lp, key):
    cc = lp.idx.get(key)
    if cc is not None:
        return (cc,)
    return tuple(c for kk, c in lp.idx.items()
                 if kk[0] == key[0] and kk[-1] == key[-1])


def cover_matrix(lp, covers):
    A, hi = lp.matrix()
    if not covers:
        return A, hi
    rows = sp.lil_matrix((len(covers), lp.base.N))
    for r, E in enumerate(covers):
        for key in E:
            for c in cols_of(lp, key):
                rows[r, c] = -1.0
    A2 = sp.vstack([A, rows.tocsr()], format='csr')
    hi2 = np.concatenate([hi, -np.ones(len(covers))])
    return A2, hi2


def select_core(lp, E, eps=1e-6):
    """Solve the dual-face selection LP on the forbidden set E."""
    A, hi = lp.matrix()
    A = A.tocsr()
    n, neq = lp.n, lp.n_eq
    r = A.shape[0] - neq
    F = set(E)
    Fcols = [cc for cc, key in enumerate(lp.cols) if key in F]
    other = [cc for cc, key in enumerate(lp.cols) if key not in F]
    if not Fcols:
        return None
    nv = neq + r + len(Fcols)
    AT = A.T.tocsr()
    Athens = sp.vstack([-AT[other], -AT[Fcols]], format='csr')
    tpart = sp.lil_matrix((len(Fcols), len(Fcols)))
    for j in range(len(Fcols)):
        tpart[j, j] = -1.0
    A_ub = sp.hstack([Athens, sp.vstack(
        [sp.csr_matrix((len(other), len(Fcols))), tpart.tocsr()])],
        format='csr')
    c = np.zeros(nv)
    c[neq + r:] = 1.0
    A_eq = np.zeros((1, nv))
    A_eq[0, neq:neq + r] = 1.0
    by = np.zeros(nv)
    by[:neq] = 1.0
    by[neq:neq + r] = hi[neq:]
    A_ub = sp.vstack([A_ub, sp.csr_matrix(by)], format='csr')
    b_ub = np.concatenate([np.zeros(A_ub.shape[0] - 1), [-eps]])
    bounds = ([(None, None)] * neq + [(0, None)] * r
              + [(0, None)] * len(Fcols))
    res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=[1.0],
                  bounds=bounds, method='highs')
    if res.status != 0:
        return None
    y = res.x[:neq + r]
    s = np.asarray(A.T.dot(y)).ravel()
    return frozenset(key for cc, key in enumerate(lp.cols)
                     if key in F and s[cc] < -1e-7)


def farkas_root(lp, covers, dens=DENS):
    """Integer Farkas certificate for the root LP with cover rows."""
    A, hi = cover_matrix(lp, covers)
    A = A.tocsr()
    n, neq = lp.n, lp.n_eq
    r = A.shape[0] - neq
    B = sp.hstack([A[:neq].T, A[neq:].T], format='csr')
    c = np.zeros(neq + r)
    c[:neq] = 1.0
    c[neq:] = hi[neq:]
    A_eq = np.zeros((1, neq + r))
    A_eq[0, neq:] = 1.0
    res = linprog(c, A_ub=-B, b_ub=np.zeros(A.shape[1]),
                  A_eq=A_eq, b_eq=[1.0],
                  bounds=[(None, None)] * neq + [(0, None)] * r,
                  method='highs')
    if res.status != 0 or res.fun >= 0:
        return None
    for D in dens:
        y = np.rint(res.x * D).astype(np.int64)
        s = np.asarray(A.T.dot(y)).ravel()
        bt = int(hi[n:].dot(y[n:])) + int(y[:n].sum())
        if s.min() >= 0 and bt < 0:
            meta = _row_meta(lp.base) + [('dom', i, j, t) for (i, j, t) in lp.cuts]
            meta += [('qc', q) for q in range(len(covers))]
            yb = y[n:]
            return dict(kind='packing', scale=D,
                        beta=[(m[1], m[2], int(yb[k])) for k, m in enumerate(meta)
                              if m[0] == 'cap' and yb[k]],
                        dom=[(m[1], m[2], m[3], int(yb[k])) for k, m in enumerate(meta)
                             if m[0] == 'dom' and yb[k]],
                        exp=[(m[1], m[2], int(yb[k])) for k, m in enumerate(meta)
                             if m[0] == 'exp' and yb[k]],
                        qc=[(m[1], int(yb[k])) for k, m in enumerate(meta)
                            if m[0] == 'qc' and yb[k]],
                        alpha=[int(v) for v in y[:n]], obj=bt,
                        farkas=res.fun)
    return None


def verify_root(lp, inst, h, cert, covers, elig_aware=False):
    """Replay an extended root certificate against base+SD+cover rows."""
    A, hi = cover_matrix(lp, covers)
    A = A.tocsr()
    n, neq = lp.n, lp.n_eq
    y = np.zeros(A.shape[0], dtype=np.int64)
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
        if q < 0 or q >= len(covers):
            return False
        y[qbase + q] += int(w)
    if y[n:].min() < 0:
        return False
    s = np.asarray(A.T.dot(y)).ravel()
    bt = int(hi[n:].dot(y[n:])) + int(y[:n].sum())
    return s.min() >= 0 and bt < 0


class QMC(QNC):
    def __init__(self, inst, h, use_cover=True, use_core=True,
                 core_cap=8, core_eps=1e-6, core_gate=1.01, **kw):
        super().__init__(inst, h, **kw)
        self.use_cover = use_cover
        self.use_core = use_core
        self.core_cap = core_cap
        self.core_eps = core_eps
        self.core_gate = core_gate
        self.covers = []
        self.cover_seen = set()
        self.cover_src = {}       # E -> certificate
        self.cover_added = 0
        self.cover_skipped = 0
        self.root_z = None
        self.root_cert = None
        self.root_checks = 0
        self.root_infeas = False
        self.core_calls = 0
        self.core_tests = 0
        self.core_shrunk = 0
        self.core_added = 0
        self.restarts = 0

    # ------------------------------------------------------------- root LP
    def _check_root(self):
        if self.lp_solves >= self.budget:
            raise Budget
        b = [(0, 1)] * self.lp.base.N
        for i, S in self.force.items():
            for key, cc in self.lp.idx.items():
                if key[0] == i and key[-1] not in S:
                    b[cc] = (0, 0)
        A, hi = cover_matrix(self.lp, self.covers)
        res = linprog(np.zeros(self.lp.base.N), A_ub=A, b_ub=hi,
                      A_eq=A[:self.lp.n_eq], b_eq=np.ones(self.lp.n),
                      bounds=b, method='highs')
        self.lp_solves += 1
        self.root_checks += 1
        if res.status == 2:
            self.root_cert = farkas_root(self.lp, self.covers)
            self.root_infeas = True
            raise Closed
        if res.status == 0:
            self.root_z = res.x
        return res

    def _add_cover(self, E, cert, root_check=True):
        E = frozenset(E)
        if not E or E in self.cover_seen:
            return False
        self.cover_seen.add(E)
        self.covers.append(E)
        self.cover_src[E] = cert
        self.cover_added += 1
        if not root_check:
            return True
        # exact gate: a cut already satisfied by the current root optimum
        # cannot change the root LP.
        if self.root_z is not None:
            zE = sum(float(self.root_z[c]) for key in E
                     for c in cols_of(self.lp, key))
            if zE >= 1.0 - 1e-9:
                self.cover_skipped += 1
                return True
        self.restarts += 1
        self._check_root()
        return True

    # ---------------------------------------------------- minimal core select
    def _select_core(self, E):
        if self.lp_solves >= self.budget:
            raise Budget
        self.core_calls += 1
        Esel = select_core(self.lp, E, eps=self.core_eps)
        self.lp_solves += 1
        self.core_tests += 1
        if not Esel or Esel == frozenset(E):
            return None, None
        cert, s = farkas_int(self.lp, Esel)
        self.lp_solves += 1
        if cert is None:
            return None, None
        E2 = frozenset(key for cc, key in enumerate(self.lp.cols)
                       if key in Esel and s[cc] < 0)
        if not E2 or not verify(self.inst, self.h, cert, forbid=E2,
                                elig_aware=self.elig):
            return None, None
        return E2, cert

    # --------------------------------------------------------------- learn
    def _learn(self, F):
        cert, E = super()._learn(F)
        if cert is None or E is None or not self.use_cover or not E:
            return cert, E
        zE0 = None
        if self.root_z is not None:
            zE0 = sum(float(self.root_z[c]) for key in E
                      for c in cols_of(self.lp, key))
        try:
            self._add_cover(E, cert)
        except Closed:
            raise
        gate_ok = (zE0 is None or self.core_gate >= 1.0
                   or zE0 < self.core_gate)
        if (self.use_core and gate_ok and not self.root_infeas and len(E) > 1
                and self.core_calls < self.core_cap):
            E2, cert2 = self._select_core(E)
            if E2 is not None and E2 != frozenset(E):
                self.core_shrunk += 1
                jobs = {key[0] for key in E2}
                if len(jobs) == 1:
                    i = next(iter(jobs))
                    times = frozenset(key[-1] for key in E2)
                    new = times & self.force.get(i, self.domain(i))
                    if new != self.force.get(i):
                        self.force[i] = new
                        if not new:
                            self.root_infeas = True
                            raise Closed
                try:
                    if self._add_cover(E2, cert2):
                        self.core_added += 1
                except Closed:
                    raise
        return cert, E

    def _solve(self, bounds, max_rounds, topk):
        res, z = super()._solve(bounds, max_rounds, topk)
        if self.root_z is None and self.nodes == 1 and res is not None \
                and res.status == 0 and z is not None:
            self.root_z = np.asarray(z)
        return res, z

    def decide(self, budget=100000, nodecap=5000, max_rounds=60, topk=100):
        self.budget = budget
        try:
            v, why = self._branch([(0, 1)] * self.lp.base.N, 0, nodecap,
                                  max_rounds, topk)
        except Closed:
            v, why = False, 'cover-root'
        except Budget:
            v, why = None, 'budget'
        return v, self._stats(why)

    def _stats(self, why):
        st = super()._stats(why)
        if why == 'cover-root':
            st['verdict'] = False
        st.update(cover_added=self.cover_added, covers=len(self.covers),
                  cover_skipped=self.cover_skipped,
                  root_checks=self.root_checks, restarts=self.restarts,
                  root_infeas=self.root_infeas,
                  core_calls=self.core_calls, core_tests=self.core_tests, core_shrunk=self.core_shrunk,
                  core_added=self.core_added,
                  root_cert_ok=(self.root_cert is not None))
        return st

    def audit(self):
        """Leaf certs at E, every cover's source, and the root certificate."""
        for F, E, c in self.leaves:
            if not E <= F:
                return False
            if E and not verify(self.inst, self.h, c, forbid=E,
                                elig_aware=self.elig):
                return False
        for E, c in self.cover_src.items():
            if not E:
                return False
            if not verify(self.inst, self.h, c, forbid=E,
                          elig_aware=self.elig):
                return False
        if self.root_infeas:
            if self.root_cert is None:
                return False
            if not verify_root(self.lp, self.inst, self.h, self.root_cert,
                               self.covers, elig_aware=self.elig):
                return False
        return True
