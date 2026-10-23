"""v8.1 QCC-ALC: quorum cover cuts with violation-triggered root checks.

v7.1 turns a leaf Farkas certificate into a clause (a set E of start-columns
that every feasible schedule must hit) and uses it only for pruning/forcing.
This module upgrades the clause to a *valid linear inequality*

    gamma(E):  sum_{c in E} z_c >= 1

and adds gamma(E) to the LP at the root.  gamma(E) is valid for every
integer schedule but can cut fractional LP points, so it is a genuine
cutting plane (a disjunctive/cover cut), not just a nogood.

The expensive object is the exact cut.  The current root LP solution z is
used as a cheap *approximate query*: if z(E) >= 1 - tol the cut is already
satisfied at the root and the root LP cannot change, so no restart LP is
spent.  Only a violated cut triggers an exact root re-solve.  If the root
LP becomes infeasible, the instance is NO and the proof is the chain of
clause certificates plus the final infeasibility certificate.

A single-job E also shrinks the domain (v7.1 force); the cover cut is then
equivalent to the force on the LP, but the root check is the new step that
can close the whole instance with one clause.
"""
import sys, time
sys.path[:0] = ['exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
import numpy as np
import scipy.sparse as sp
from scipy.optimize import linprog
from qnc import QNC, Budget, farkas_int
from cert import verify


class Closed(Exception):
    pass


def cols_of(lp, key):
    cc = lp.idx.get(key)
    if cc is not None:
        return (cc,)
    return tuple(c for kk, c in lp.idx.items()
                 if kk[0] == key[0] and kk[-1] == key[1])


def cover_matrix(lp, covers):
    """Base+SD matrix plus one row -sum_{c in E} z_c <= -1 per cover."""
    A, hi = lp.matrix()
    if not covers:
        return A, hi
    rows = []
    for E in covers:
        row = np.zeros(lp.N)
        for key in E:
            for c in cols_of(lp, key):
                row[c] = -1.0
        rows.append(sp.csr_matrix(row))
    A2 = sp.vstack([A] + rows).tocsr()
    hi2 = np.concatenate([hi, -np.ones(len(rows))])
    return A2, hi2


def root_solve(lp, covers, force, h):
    A, hi = cover_matrix(lp, covers)
    bounds = [(0, 1)] * lp.N
    for i, S in force.items():
        for key, c in lp.idx.items():
            if key[0] == i and key[-1] not in S:
                bounds[c] = (0, 0)
    res = linprog(np.zeros(lp.N), A_ub=A, b_ub=hi,
                  A_eq=A[:lp.n_eq], b_eq=np.ones(lp.n),
                  bounds=bounds, method='highs')
    return res


class QCC(QNC):
    def __init__(self, inst, h, use_cover=True, use_restart=True,
                 root_gate=True, **kw):
        super().__init__(inst, h, **kw)
        self.use_cover = use_cover
        self.use_restart = use_restart
        self.root_gate = root_gate
        self.covers = []                 # list of frozenset E
        self.root_z = None
        self.root_checks = 0
        self.root_lp = 0
        self.root_infeas = False
        self.restarts = 0
        self.cover_added = 0
        self.cover_skipped = 0
        self.root_t = 0.0
        self._cover_seen = set()

    # ---------------------------------------------------------- LP at root
    def _check_root(self, newE=None):
        """Exact root re-solve with all cover cuts and force."""
        t0 = time.time()
        if self.lp_solves >= self.budget:
            raise Budget
        res = root_solve(self.lp, self.covers, self.force, self.h)
        self.lp_solves += 1
        self.root_checks += 1
        self.root_lp += 1
        self.root_t += time.time() - t0
        if res.status == 2:
            self.root_infeas = True
            raise Closed
        if res.status != 0:
            return None
        self.root_z = res.x
        return res

    def _learn(self, F):
        got = super()._learn(F)
        cert, E = got
        if cert is None or E is None or not self.use_cover:
            return got
        if not E:
            return got
        # only genuinely new clauses
        key = frozenset(E)
        if key in self._cover_seen:
            self.cover_skipped += 1
            return got
        self._cover_seen.add(key)
        self.covers.append(key)
        self.cover_added += 1
        if not self.use_restart:
            return got
        # cheap approximate query: is the new cut violated at the root?
        if self.root_gate and self.root_z is not None:
            zE = sum(float(self.root_z[c]) for k in E for c in cols_of(self.lp, k))
            if zE >= 1.0 - 1e-9:
                self.cover_skipped += 1
                return got
        # exact query / restart
        self.restarts += 1
        self._check_root(key)
        return got

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

    def _solve(self, bounds, max_rounds, topk):
        res, z = super()._solve(bounds, max_rounds, topk)
        # record the root solution for the approximate gate; _branch calls
        # root with depth 0, and _solve does not know depth, so use first
        # feasible solve while nodes==1.
        if self.root_z is None and self.nodes == 1 and res is not None \
                and res.status == 0 and z is not None:
            self.root_z = np.asarray(z)
        return res, z

    def _stats(self, why):
        st = super()._stats(why)
        if why == 'cover-root':
            st['verdict'] = False
        st.update(covers=len(self.covers), cover_added=self.cover_added,
                  cover_skipped=self.cover_skipped,
                  root_checks=self.root_checks, root_lp=self.root_lp,
                  restarts=self.restarts, root_infeas=self.root_infeas,
                  root_t=self.root_t)
        return st
