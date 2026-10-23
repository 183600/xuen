"""QCC with Farkas-weighted cover cuts.

For a Farkas certificate y at a node, let sigma_c=(A^T y)_c and
E={c in F: sigma_c<0}.  For every feasible z, b^T y = sum_c sigma_c z_c < 0
and sigma_c>=0 outside E, so

    sum_{c in E} w_c z_c > sum_{c not in E} sigma_c z_c >= 0,
    w_c = -sigma_c > 0.

For an *integer* schedule z is a 0/1 vector (one start per job), hence the
left side is either 0 or at least w_min = min_{c in E} w_c.  Therefore

    gamma_w(E):  sum_{c in E} w_c z_c >= w_min

is a valid inequality.  w=1 gives v7.1's uniform cover cut; general w is a
Farkas-weighted cover cut.  Both are rank-1 integrality cuts.
"""
import sys, time
sys.path[:0] = ['exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
import numpy as np
import scipy.sparse as sp
from scipy.optimize import linprog
from qnc import QNC, Budget, farkas_int
from cert import verify
from qcc import cols_of, Closed


class QCC2(QNC):
    def __init__(self, inst, h, cut_kind='both', use_restart=True,
                 root_gate=True, **kw):
        super().__init__(inst, h, **kw)
        self.cut_kind = cut_kind          # 'uniform' | 'weighted' | 'both'
        self.use_restart = use_restart
        self.root_gate = root_gate
        self.covers = []                  # (frozenset E, dict key->weight)
        self.root_z = None
        self.root_checks = self.root_lp = 0
        self.restarts = self.cover_added = self.cover_skipped = 0
        self.root_t = 0.0
        self.last_sigma = None
        self._cover_seen = set()

    def _analyse(self, F):
        t0 = time.time()
        self.cert_calls += 1
        cert, s = farkas_int(self.lp, F)
        self.cert_t += time.time() - t0
        if cert is None:
            self.cert_fail += 1
            return None
        E = frozenset(key for cc, key in enumerate(self.lp.cols)
                      if key in F and s[cc] < 0)
        if E != frozenset(F) and not verify(self.inst, self.h, cert, forbid=E,
                                            elig_aware=self.elig):
            E = frozenset(F)
        self.last_sigma = s
        return cert, E

    def _add_covers(self, E):
        sig = self.last_sigma
        wk = {key: -int(sig[self.lp.idx[key]]) for key in E}
        # eligibility: sigma of the first copy; all copies share the row
        if self.cut_kind in ('uniform', 'both'):
            self.covers.append((frozenset(E), {key: 1 for key in E}, 1))
        if self.cut_kind in ('weighted', 'both'):
            wmin = min(wk.values())
            self.covers.append((frozenset(E), wk, wmin))

    def _root_solve(self):
        A, hi = self.lp.matrix()
        rows = []
        for E, wk, rhs in self.covers:
            row = np.zeros(self.lp.N)
            for key in E:
                for c in cols_of(self.lp, key):
                    row[c] = -wk[key]
            rows.append(sp.csr_matrix(row))
        if rows:
            A = sp.vstack([A] + rows).tocsr()
            hi = np.concatenate([hi, -np.array([r[2] for r in self.covers],
                                               dtype=float)])
        bounds = [(0, 1)] * self.lp.N
        for i, S in self.force.items():
            for key, c in self.lp.idx.items():
                if key[0] == i and key[-1] not in S:
                    bounds[c] = (0, 0)
        return linprog(np.zeros(self.lp.N), A_ub=A, b_ub=hi,
                       A_eq=A[:self.lp.n_eq], b_eq=np.ones(self.lp.n),
                       bounds=bounds, method='highs')

    def _check_root(self):
        t0 = time.time(); self.root_checks += 1; self.root_lp += 1
        if self.lp_solves >= self.budget:
            raise Budget
        res = self._root_solve()
        self.lp_solves += 1
        self.root_t += time.time() - t0
        if res.status == 2:
            raise Closed
        if res.status == 0:
            self.root_z = res.x
        return res

    def _learn(self, F):
        cert, E = super()._learn(F)
        if cert is None or E is None or not E:
            return cert, E
        key = frozenset(E)
        if key in self._cover_seen:
            self.cover_skipped += 1
            return cert, E
        self._cover_seen.add(key)
        self._add_covers(E)
        self.cover_added += 1
        if not self.use_restart:
            return cert, E
        if self.root_gate and self.root_z is not None:
            # violation of the uniform relaxation of the new clause
            zE = sum(float(self.root_z[c]) for k in E
                     for c in cols_of(self.lp, k))
            if zE >= 1.0 - 1e-9:
                self.cover_skipped += 1
                return cert, E
        self.restarts += 1
        self._check_root()
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
        st.update(covers=len(self.covers), cover_added=self.cover_added,
                  cover_skipped=self.cover_skipped,
                  root_checks=self.root_checks, root_lp=self.root_lp,
                  restarts=self.restarts, root_t=self.root_t)
        return st
