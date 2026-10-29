"""v7.3 QCC-ALC: quorum clauses as a CSP + case branching + cover check.

v7.1 learned a globally valid clause from every infeasible leaf:

    E = {(i,t) : t in E_i}      LP(D \\ E) infeasible
    every feasible schedule satisfies  OR_i (s_i in E_i).

It used the clause only for the full-falsification test E subset F and for
the singleton-job force.  That test almost never fires under threshold
branching (0/201 in v7.1).  This module treats the clauses as a real
multi-valued CSP:

  * unit propagation: if all but one literal of a clause are dead in the
    current domains, intersect the remaining job domain with its literal;
  * case branching: for a clause with k live literals, partition the
    current domain space into k "first satisfied literal" cases plus one
    "all literals falsified" case.  The last case is closed for free by
    the quorum lemma, without an LP;
  * cover check: the clause family is tested against the LP feasible
    region.  tau < 1 certifies NO by a mixture of quorum certificates.

The worst case is exponential (a case split removes at least one start
value from a domain), but every LP-infeasible node still returns an exact
integer Farkas certificate.  Clauses, force and decisions are monotone.
"""
import sys, time, collections
from fractions import Fraction
sys.path[:0] = ['exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
import numpy as np
from scipy.optimize import linprog
from qnc import QNC, Budget, farkas_int
from cert import verify


class CoverClosed(Exception):
    pass


def cols_of(lp, key):
    cc = lp.idx.get(key)
    if cc is not None:
        return (cc,)
    return tuple(c for kk, c in lp.idx.items()
                 if kk[0] == key[0] and kk[-1] == key[1])


def _rat(x, maxden=10 ** 6):
    return Fraction(float(x)).limit_denominator(maxden)


def _gcd(a, b):
    while b:
        a, b = b, a % b
    return abs(a)


def mix_certificate(lp, clauses, res, maxden=10 ** 6):
    """Exact rational dual mixture for the cover LP.

    Follows the construction in v8.0: the dual of

        max lambda  s.t.  A z <= b, Aeq z = 1,
                          sum_{c in E^k} z_c >= lambda,
                          0 <= z <= 1

    is a distribution pi over the clauses plus scheduling duals.  We
    rationalise the HiGHS marginals and replay the column inequalities
    exactly; returns None if reconstruction fails.
    """
    A, hi = lp.matrix()
    N = lp.base.N
    n_eq = lp.n_eq
    y = [_rat(-v, maxden) for v in res.ineqlin.marginals]
    nu = [_rat(-v, maxden) for v in res.eqlin.marginals]
    mu = [_rat(-v, maxden) for v in res.upper.marginals[:N]]
    if any(v < 0 for v in y) or any(v < 0 for v in mu):
        return None
    pi = y[A.shape[0]:]
    S = sum(pi)
    if S <= 0:
        return None
    for c in range(N):
        lhs = sum(Fraction(int(A[r, c])) * y[r] for r in range(A.shape[0]))
        lhs += sum(Fraction(int(A[r, c])) * nu[r] for r in range(n_eq))
        lhs += mu[c]
        rhs = Fraction(0)
        for k, E in enumerate(clauses):
            if any(c in cols_of(lp, key) for key in E):
                rhs += pi[k]
        if lhs < rhs:
            return None
    obj = sum(Fraction(int(hi[n_eq + r])) * y[n_eq + r]
              for r in range(A.shape[0] - n_eq))
    obj += sum(nu) + sum(mu)
    if not (obj < S):
        return None
    den = 1
    for v in list(y) + list(nu) + list(mu):
        den = den * v.denominator // _gcd(den, v.denominator)
    return dict(pi=[int(v * den) for v in pi],
                y=[int(v * den) for v in y],
                nu=[int(v * den) for v in nu],
                mu=[int(v * den) for v in mu],
                S=int(S * den), obj=int(obj * den), den=den)


def replay_mixture(lp, clauses, mc):
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


class QCC(QNC):
    def __init__(self, inst, h, case_on=True, case_k=2, case_order='small',
                 case_min=2, use_prop=True, use_cover=False, cover_gate=True,
                 cover_eps=1e-6, case_policy='tight', case_max_ratio=0.6,
                 cover_min_k=1, **kw):
        super().__init__(inst, h, **kw)
        self.case_on = case_on
        self.case_k = case_k
        self.case_order = case_order
        self.case_min = case_min
        self.use_prop = use_prop
        self.use_cover = use_cover
        self.cover_gate = cover_gate
        self.cover_eps = cover_eps
        self.case_policy = case_policy
        self.case_max_ratio = case_max_ratio
        self.cover_min_k = cover_min_k

        self.clause_db = []          # dict job -> frozenset(start times)
        self.clause_meta = []        # (E frozenset, cert, F frozenset)
        self.by_job = collections.defaultdict(list)
        self._root_dom = {i: set(S) for i, S in self._dom.items()}

        self.prop_steps = 0
        self.prop_conflicts = 0
        self.case_branches = 0
        self.case_children = 0
        self.case_free = 0
        self.cover_calls = 0
        self.cover_hits = 0
        self.cover_tau = None
        self.cover_proof = None
        self._last_cover_res = None
        self.clause_leaves = []      # (clause index, domain snapshot)
        self.case_records = []       # (job order, domains) for split audit
        self.global_no = False

    def _analyse(self, F):
        import time
        t0 = time.time()
        self.cert_calls += 1
        cert, s = farkas_int(self.lp, F)
        self.cert_t += time.time() - t0
        if cert is None:
            self.cert_fail += 1
            return None
        E = frozenset((key[0], key[-1]) for cc, key in enumerate(self.lp.cols)
                      if (key[0], key[-1]) in F and s[cc] < 0)
        if E != frozenset(F) and not verify(self.inst, self.h, cert,
                                            forbid=E, elig_aware=self.elig):
            E = frozenset(F)
        return cert, E

    # ------------------------------------------------------------- clauses
    def _norm(self, E):
        d = {}
        for (i, t) in E:
            d.setdefault(i, set()).add(t)
        out = {}
        for i, S in d.items():
            S = frozenset(S)
            if not S:
                continue
            if S >= self._root_dom[i]:
                return None          # tautology
            out[i] = S
        return out

    def _add_clause(self, E, cert, F):
        if not E:
            return None
        C = self._norm(E)
        if C is None:
            return None
        for old in self.clause_db:
            # old subsumes C: old is stronger, C is redundant
            if set(old) <= set(C) and all(old[i] <= C[i] for i in old):
                return None
        idx = len(self.clause_db)
        self.clause_db.append(C)
        self.clause_meta.append((frozenset(E), cert, frozenset(F)))
        for i in C:
            self.by_job[i].append(idx)
        return idx

    def _learn(self, F):
        cert, E = super()._learn(F)
        if E:
            self._add_clause(E, cert, F)
        else:
            self.global_no = True
        return cert, E

    # ---------------------------------------------------------- propagation
    def _propagate(self, dom):
        """Arc consistency for the clause set.  Returns (conflict_ci, dom)."""
        if not self.use_prop:
            return None, dom
        changed = True
        while changed:
            changed = False
            for ci, C in enumerate(self.clause_db):
                live = []
                sat = False
                for i, S in C.items():
                    inter = dom[i] & S
                    if not inter:
                        continue
                    if dom[i] <= S:
                        sat = True
                        break
                    live.append((i, inter))
                if sat:
                    continue
                if not live:
                    self.prop_conflicts += 1
                    return ci, dom
                if len(live) == 1:
                    i, inter = live[0]
                    if inter != dom[i]:
                        dom[i] = set(inter)
                        self.prop_steps += 1
                        changed = True
                        if not dom[i]:
                            self.prop_conflicts += 1
                            return ci, dom
        return None, dom

    # ------------------------------------------------------------ cover LP
    def _cover_lp(self):
        if len(self.clause_db) < self.cover_min_k:
            return None
        A, hi = self.lp.matrix()
        N = self.lp.N
        K = len(self.clause_db)
        A_ub = np.zeros((A.shape[0] + K, N + 1))
        b_ub = np.zeros(A.shape[0] + K)
        A_ub[:A.shape[0], :N] = A.toarray()
        b_ub[:A.shape[0]] = hi
        for k, C in enumerate(self.clause_db):
            for i, S in C.items():
                for t in S:
                    for cc in cols_of(self.lp, (i, t)):
                        A_ub[A.shape[0] + k, cc] -= 1.0
            A_ub[A.shape[0] + k, N] = 1.0
        A_eq = np.zeros((self.lp.n, N + 1))
        A_eq[:, :N] = A[:self.lp.n_eq].toarray()
        c = np.zeros(N + 1)
        c[N] = -1.0
        res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq,
                      b_eq=np.ones(self.lp.n),
                      bounds=[(0, 1)] * N + [(0, 1)], method='highs')
        self.cover_calls += 1
        if res.status != 0:
            return None
        self._last_cover_res = res
        return -res.fun, res.x[:N]

    def _cover_check(self):
        if not self.use_cover:
            return False
        got = self._cover_lp()
        if got is None:
            return False
        tau, z = got
        self.cover_tau = tau
        if tau < 1.0 - self.cover_eps:
            self.cover_hits += 1
            clauses = [frozenset((i, t) for i, S in C.items() for t in S)
                       for C in self.clause_db]
            self.cover_proof = (clauses, self._last_cover_res)
            self.global_no = True
            return True
        return False

    # ------------------------------------------------------------ branching
    def _dom_from_bounds(self, bounds):
        dom = {i: set() for i in range(self.n)}
        for key, cc in self.lp.idx.items():
            if bounds[cc] != (0, 0):
                dom[key[0]].add(key[-1])
        return dom

    def _bounds_from_dom(self, dom):
        return [(0, 1) if key[-1] in dom[key[0]] else (0, 0)
                for key in self.lp.cols]

    def _case_candidate(self, dom):
        if not self.case_on:
            return None
        cand = []
        for ci, C in enumerate(self.clause_db):
            live = []
            sat = False
            for i, S in C.items():
                inter = dom[i] & S
                if not inter:
                    continue
                if dom[i] <= S:
                    sat = True
                    break
                live.append((i, frozenset(inter), S))
            if sat or not (self.case_min <= len(live) <= self.case_k):
                continue
            if max(len(x) / max(1, len(dom[i])) for i, x, _ in live) > self.case_max_ratio:
                continue
            # tight: few live literals; small total live mass; small complement
            mass = sum(len(x[1]) for x in live)
            comp = sum(len(dom[i]) - len(x) for i, x, _ in live)
            cand.append((len(live), mass, comp, ci, live))
        if not cand:
            return None
        cand.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
        return cand[0][3], cand[0][4]

    def _order_live(self, live):
        if self.case_order == 'small':
            return sorted(live, key=lambda x: (len(x[1]), x[0]))
        if self.case_order == 'large':
            return sorted(live, key=lambda x: (-len(x[1]), x[0]))
        if self.case_order == 'balance':
            return sorted(live, key=lambda x: (abs(len(x[1]) - len(x[1]) / 2.0),
                                               x[0]))
        return list(live)

    def _record_clause_leaf(self, ci, dom):
        self.clause_leaves.append(
            (ci, {i: frozenset(S) for i, S in dom.items()}))
        for i, S in self.clause_db[ci].items():
            if S & dom[i]:
                return
        return

    def _median_split(self, dom, z):
        frac = []
        for cc, key in enumerate(self.lp.cols):
            if key[-1] not in dom[key[0]]:
                continue
            if 1e-7 < z[cc] < 1 - 1e-7:
                frac.append((abs(z[cc] - 0.5), cc, key[0], key[-1]))
        if not frac:
            return None
        frac.sort()
        _, cc, i, t = frac[0]
        times = sorted(dom[i])
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
        A = frozenset(tt for tt in times if tt <= mid)
        B = frozenset(tt for tt in times if tt > mid)
        if not A or not B:
            return None
        return i, A, B

    def _branch(self, bounds, depth, nodecap, max_rounds, topk):
        if self.global_no:
            return False, 'cover-global'
        dom = self._dom_from_bounds(bounds)
        # global force from v7.1 remains valid; clauses also encode it
        for i, S in self.force.items():
            dom[i] &= set(S)
        ci, dom = self._propagate(dom)
        if ci is not None:
            self._record_clause_leaf(ci, dom)
            return False, 'clause'
        if any(not dom[i] for i in range(self.n)):
            self.empty_prunes += 1
            return False, 'empty'
        b = self._bounds_from_dom(dom)
        F = self._forbids(b)
        for E in self.clauses:
            if E <= F:
                self.prunes += 1
                return False, 'clause'
        self.nodes += 1
        if self.nodes > nodecap:
            raise Budget
        res, z = self._solve(b, max_rounds, topk)
        if res.status == 2:
            self._learn(F)
            if self._cover_check():
                return False, 'cover'
            return False, 'no'
        if z is None:
            return None, 'roundcap'
        frac = []
        for cc, key in enumerate(self.lp.cols):
            if key[-1] not in dom[key[0]]:
                continue
            if 1e-7 < z[cc] < 1 - 1e-7:
                frac.append((abs(z[cc] - 0.5), cc, key[0], key[-1]))
        if not frac:
            return True, 'yes'

        cand = self._case_candidate(dom)
        if cand is not None:
            ci2, live = cand
            live = self._order_live(live)
            self.case_branches += 1
            children = []
            for r, (i, inter, S) in enumerate(live):
                child = {j: set(v) for j, v in dom.items()}
                for j, _, Sj in live[:r]:
                    child[j] -= Sj
                child[i] &= S
                children.append(child)
            last = {j: set(v) for j, v in dom.items()}
            for j, _, Sj in live:
                last[j] -= Sj
            children.append(last)
            self.case_records.append(
                (ci2, tuple(x[0] for x in live),
                 {j: set(v) for j, v in dom.items()},
                 [{j: set(v) for j, v in c.items()} for c in children]))
            self.case_children += len(children) - 1
            for r, child in enumerate(children[:-1]):
                if not child[live[r][0]]:
                    self.empty_prunes += 1
                    a, why = False, 'empty'
                else:
                    a, why = self._branch(self._bounds_from_dom(child),
                                          depth + 1, nodecap, max_rounds, topk)
                if a is not False:
                    return a, why
            # all literals falsified: quorum lemma, no LP
            self.case_free += 1
            self._record_clause_leaf(ci2, last)
            return False, 'case-free'

        got = self._median_split(dom, z)
        if got is None:
            # fall back to the first fractional column
            _, cc, i, t = frac[0]
            times = sorted(dom[i])
            mid = t
            if mid >= times[-1]:
                mid = times[-1] - 1
            A = frozenset(tt for tt in times if tt <= mid)
            B = frozenset(tt for tt in times if tt > mid)
        else:
            i, A, B = got
        left = {j: set(v) for j, v in dom.items()}
        left[i] &= set(A)
        right = {j: set(v) for j, v in dom.items()}
        right[i] &= set(B)
        a, why = self._branch(self._bounds_from_dom(left), depth + 1,
                              nodecap, max_rounds, topk)
        if a is not False:
            return a, why
        return self._branch(self._bounds_from_dom(right), depth + 1,
                            nodecap, max_rounds, topk)

    def decide(self, budget=100000, nodecap=5000, max_rounds=60, topk=100):
        self.budget = budget
        try:
            v, why = self._branch([(0, 1)] * self.lp.base.N, 0, nodecap,
                                  max_rounds, topk)
        except Budget:
            v, why = None, 'budget'
        except CoverClosed:
            v, why = False, 'cover'
        return v, self._stats(why)

    # --------------------------------------------------------------- stats
    def _stats(self, why):
        st = super()._stats(why)
        st.update(prop_steps=self.prop_steps, prop_conflicts=self.prop_conflicts,
                  case_branches=self.case_branches,
                  case_children=self.case_children,
                  case_free=self.case_free,
                  cover_calls=self.cover_calls, cover_hits=self.cover_hits,
                  cover_tau=self.cover_tau,
                  clause_db=len(self.clause_db),
                  clause_leaves=len(self.clause_leaves),
                  case_records=len(self.case_records))
        return st

    def audit(self):
        # 1. every Farkas leaf replays at its essential scope
        for F, E, c in self.leaves:
            if not E <= F:
                return False
            if not verify(self.inst, self.h, c, forbid=E,
                          elig_aware=self.elig):
                return False
        # 2. every stored clause replays at E
        for E, c, F in self.clause_meta:
            if not verify(self.inst, self.h, c, forbid=E,
                          elig_aware=self.elig):
                return False
        # 3. every clause leaf is really falsified
        for ci, dom in self.clause_leaves:
            C = self.clause_db[ci]
            for i, S in C.items():
                if S & dom[i]:
                    return False
        # 4. every case split covers its parent domain
        for ci, order, parent, children in self.case_records:
            C = self.clause_db[ci]
            k = len(order)
            for r in range(k):
                for pos, j in enumerate(order):
                    if pos < r:
                        expect = parent[j] - C[j]
                    elif pos == r:
                        expect = parent[j] & C[j]
                    else:
                        expect = parent[j]
                    if children[r][j] != expect:
                        return False
            for j in order:
                if children[k][j] != parent[j] - C[j]:
                    return False
            for ch in children:
                for j in parent:
                    if not ch[j] <= parent[j]:
                        return False
                for j in parent:
                    if j not in order and ch[j] != parent[j]:
                        return False
            for a in range(k + 1):
                for b in range(a + 1, k + 1):
                    if all(children[a][j] == children[b][j] for j in order):
                        return False
        # 5. exact replay of the mixture certificate, if cover closed
        if self.cover_hits:
            if self.cover_proof is None:
                return False
            clauses, res = self.cover_proof
            mc = mix_certificate(self.lp, clauses, res)
            if mc is None:
                return False
            if not replay_mixture(self.lp, clauses, mc):
                return False
        return True
