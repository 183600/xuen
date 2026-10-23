"""v8.0 QCM-ALC: quorum cover mixture.

v7.1 used a leaf certificate's essential scope E only as a *constraint*
(prune nodes whose forbid set contains E, shrink a unit domain).  It never
asked the complementary question:

    is the region where the clause is satisfied itself feasible?

For a clause family K = {E^1..E^K} define the cover LP

    tau(K) = max lambda
             s.t.  A z <= b,  A_eq z = 1,  0 <= z <= 1     (scheduling LP)
                   sum_{c in E^k} z_c >= lambda   for all k.

Every feasible integral schedule hits every clause, so it is a point with
lambda = 1; hence tau(K) < 1  =>  NO.  The dual of the cover LP is a
probability distribution pi over the clauses (sum pi = 1) plus scheduling
duals, i.e. a *mixture of quorums* that is itself infeasible: the
multi-certificate object v7.1 predicted was necessary.

tau is monotone non-increasing in K and tau(K) <= min_E tau({E}), so a
single clause whose own region is infeasible already closes the instance.
The cover LP is run as an online probe on the DFS clause stream.
"""
import sys, time
sys.path[:0] = ['exp/v61', 'exp/v60', 'exp/v13']
import numpy as np
from scipy.optimize import linprog
from qnc import QNC, Budget


class Proved(Exception):
    pass


def cols_of(lp, key):
    """All LP columns for a start-time key (i,t).

    Eligibility-aware LPs key columns by (i,k,t); a clause is a statement
    about start times, so it constrains every eligible machine copy.
    """
    cc = lp.idx.get(key)
    if cc is not None:
        return (cc,)
    return tuple(c for kk, c in lp.idx.items()
                 if kk[0] == key[0] and kk[-1] == key[1])


def cover_lp(lp, clauses):
    """Return (tau, res) for the cover LP over the given schedule LP.

    tau < 1 certifies NO.  res is the raw HiGHS result (duals for the
    mixture certificate).  An empty clause gives tau = 0.
    """
    if any(len(E) == 0 for E in clauses):
        return 0.0, None
    A, hi = lp.matrix()
    N = lp.base.N
    K = len(clauses)
    A_ub = np.zeros((A.shape[0] + K, N + 1))
    b_ub = np.zeros(A.shape[0] + K)
    A_ub[:A.shape[0], :N] = A.toarray()
    b_ub[:A.shape[0]] = hi
    for k, E in enumerate(clauses):
        for key in E:
            for cc in cols_of(lp, key):
                A_ub[A.shape[0] + k, cc] = -1.0
        A_ub[A.shape[0] + k, N] = 1.0
    A_eq = np.zeros((lp.n, N + 1))
    A_eq[:, :N] = A[:lp.n_eq].toarray()
    c = np.zeros(N + 1)
    c[N] = -1.0
    res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=np.ones(lp.n),
                  bounds=[(0, 1)] * N + [(0, None)], method='highs')
    if res.status != 0:
        return None, res
    return -res.fun, res


class QCM(QNC):
    def __init__(self, inst, h, probe='each', eps=0.0, cover_on=True, **kw):
        super().__init__(inst, h, **kw)
        self.probe = probe          # 'each' | 'multi' | 'none'
        self.eps = eps              # stop at tau < 1 - eps (sound)
        self.cover_on = cover_on
        self.cover_lp = 0
        self.cover_t = 0.0
        self.probes = []            # (nclauses, tau, lp_solves, nodes)
        self.mix = None             # (clauses, tau, res) at the stop
        self.stopped = False
        self.witness = None         # last feasible fractional schedule
        self.pool = []              # bounded pool of feasible schedules
        self.skipped = 0            # probes skipped by a hitting witness

    def _pool_hits_all(self):
        for z in self.pool:
            ok = True
            for E in self.clauses:
                cols = [cc for c in E for cc in cols_of(self.lp, c)]
                if sum(z[cc] for cc in cols) < 1.0 - 1e-9:
                    ok = False
                    break
            if ok:
                return True
        return False

    def _should_probe(self):
        K = len(self.clauses)
        if not self.cover_on or self.probe == 'none' or K == 0:
            return False
        if self.probe == 'multi':
            return K >= 2
        return True                    # 'each'

    def _learn(self, F):
        r = super()._learn(F)
        if r[1] is None:               # extraction failed
            return r
        if self.stopped or not self._should_probe():
            return r
        # Streaming filter: a feasible fractional schedule z with
        # z(E) >= 1 witnesses tau({E}) >= 1, so no probe can help yet.
        # A feasible z that hits *every* clause proves tau(K) >= 1; only
        # then is the joint probe provably useless.  Checking just the new
        # clause would be wrong: single clauses can each be satisfiable
        # while their mixture is not (the synergy case).
        if self.pool and self._pool_hits_all():
            self.skipped += 1
            return r
        t0 = time.time()
        tau, res = cover_lp(self.lp, self.clauses)
        self.cover_t += time.time() - t0
        self.cover_lp += 1
        self.probes.append((len(self.clauses),
                            None if tau is None else float(tau),
                            self.lp_solves, self.nodes))
        if tau is not None and tau < 1.0 - self.eps - 1e-9:
            self.mix = (list(self.clauses), float(tau), res)
            self.stopped = True
            raise Proved
        return r

    def _solve(self, bounds, max_rounds, topk):
        res, z = super()._solve(bounds, max_rounds, topk)
        if z is not None and res is not None and res.status == 0:
            zz = np.asarray(z)
            self.witness = zz
            if len(self.pool) < 64:
                self.pool.append(zz)
        return res, z

    def decide(self, budget=100000, nodecap=5000, max_rounds=60, topk=100):
        self.budget = budget
        try:
            v, why = self._branch([(0, 1)] * self.lp.base.N, 0, nodecap,
                                  max_rounds, topk)
        except Proved:
            v, why = False, 'cover'
        except Budget:
            v, why = None, 'budget'
        return v, self._stats(why)

    def _stats(self, why):
        st = super()._stats(why)
        if why == 'cover':
            st['verdict'] = False
        st.update(cover_lp=self.cover_lp, cover_t=self.cover_t,
                  probes=self.probes, stopped=self.stopped,
                  skipped=self.skipped,
                  tau=(None if self.mix is None else self.mix[1]),
                  nclauses=len(self.clauses))
        return st

    def audit_full(self):
        if not self.audit():
            return False
        if self.mix is not None:
            clauses, tau, res = self.mix
            mc = mix_certificate(self.lp, clauses, res)
            if mc is None:
                return False
            if not replay_mixture(self.lp, clauses, mc):
                return False
        return True


# ------------------------------------------------------------------ audit
from fractions import Fraction


def _rat(x, maxden=10 ** 6):
    return Fraction(float(x)).limit_denominator(maxden)


def mix_certificate(lp, clauses, res, maxden=10 ** 6):
    """Turn HiGHS duals of the cover LP into an exact rational mixture.

    Returns dict(pi, y, nu, mu, S, obj) with integer entries after scaling,
    or None if rational reconstruction fails the exact replay.
    """
    A, hi = lp.matrix()
    N = lp.base.N
    n_eq = lp.n_eq
    K = len(clauses)
    y = [_rat(-v, maxden) for v in res.ineqlin.marginals]
    nu = [_rat(-v, maxden) for v in res.eqlin.marginals]
    mu = [_rat(-v, maxden) for v in res.upper.marginals[:N]]
    if any(v < 0 for v in y) or any(v < 0 for v in mu):
        return None
    pi = y[A.shape[0]:]
    S = sum(pi)
    if S <= 0:
        return None
    # exact column inequality  A^T y + Aeq^T nu + mu >= sum_k pi_k 1_{E^k}
    slack_min = None
    for c in range(N):
        lhs = sum(Fraction(int(A[r, c])) * y[r] for r in range(A.shape[0]))
        lhs += sum(Fraction(int(A[r, c])) * nu[r] for r in range(n_eq))
        lhs += mu[c]
        rhs = Fraction(0)
        for k, E in enumerate(clauses):
            if any(c in cols_of(lp, key) for key in E):
                rhs += pi[k]
        sl = lhs - rhs
        if slack_min is None or sl < slack_min:
            slack_min = sl
        if sl < 0:
            return None
    obj = sum(Fraction(int(hi[n_eq + r])) * y[n_eq + r]
              for r in range(A.shape[0] - n_eq))
    obj += sum(nu) + sum(mu)
    if not (obj < S):
        return None
    # integer scale
    den = 1
    for v in list(y) + list(nu) + list(mu):
        den = den * v.denominator // _gcd(den, v.denominator)
    return dict(pi=[int(v * den) for v in pi],
                y=[int(v * den) for v in y],
                nu=[int(v * den) for v in nu],
                mu=[int(v * den) for v in mu],
                S=int(S * den), obj=int(obj * den), den=den,
                slack_min=int(slack_min * den))


def _gcd(a, b):
    while b:
        a, b = b, a % b
    return abs(a)


def replay_mixture(lp, clauses, mc):
    """Exact integer replay of a mixture certificate (no floats)."""
    A, hi = lp.matrix()
    N = lp.base.N
    n_eq = lp.n_eq
    y, nu, mu = mc['y'], mc['nu'], mc['mu']
    if mc['S'] <= 0 or any(v < 0 for v in y) or any(v < 0 for v in mu):
        return False
    if any(v < 0 for v in mc['pi']) or sum(mc['pi']) != mc['S']:
        return False
    for c in range(N):
        lhs = sum(int(A[r, c]) * y[r] for r in range(A.shape[0]))
        lhs += sum(int(A[r, c]) * nu[r] for r in range(n_eq))
        lhs += mu[c]
        rhs = 0
        for k, E in enumerate(clauses):
            if any(c in cols_of(lp, key) for key in E):
                rhs += mc['pi'][k]
        if lhs < rhs:
            return False
    obj = sum(int(hi[n_eq + r]) * y[n_eq + r]
              for r in range(A.shape[0] - n_eq))
    obj += sum(nu) + sum(mu)
    return obj < mc['S']
