"""SD-ECC v6.0: start-time LP with stochastic-dominance precedence cuts.

Primal (full eligibility):
  z[i,t] in [0,1]       job i starts at t
  sum_t z[i,t] = 1
  sum_i sum_{s<=t<s+p_i} z[i,s] <= m              (time capacity)
  sum_{s<=t} z[i,s] >= sum_{s<=t+p_i} z[j,s]      (i -> j dominance)

The last row is the correct cumulative form of precedence: if j starts by
t+p_i then i must have started by t.  It replaces the weaker expectation
row E[s_i] + p_i <= E[s_j] used by v5.0 ECC.  When eligibility is present
each job also chooses a machine k and capacity is per machine.

The dual is a packing of time cuts beta_t and dominance cuts lambda_{ij,t};
lambda behaves like a flow on the time axis of each precedence edge.
"""
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import lil_matrix

try:
    from po import heads_tails
except Exception:  # direct script use
    import sys
    sys.path[:0] = ['exp/v13']
    from po import heads_tails


class SDLP:
    def __init__(self, inst, T, est=None, q=None, use_expect=False,
                 use_dom=True, elig_aware=False, forbid=None):
        self.inst = inst
        self.T = T
        self.n = inst['n']
        self.m = inst['m']
        self.p = inst['p']
        self.use_expect = use_expect
        self.use_dom = use_dom
        self.elig_aware = elig_aware
        if est is None or q is None:
            est, q = heads_tails(inst, 0, [0] * self.n)
        self.est, self.q = est, q
        self.elig = ([sorted(set(e)) for e in inst['elig']] if elig_aware
                     else [list(range(self.m)) for _ in range(self.n)])
        self.forbid = set(forbid or ())
        self.idx = {}
        self.cols = []
        for i in range(self.n):
            machines = self.elig[i] if elig_aware else [None]
            for k in machines:
                for t in range(est[i], T - q[i] - self.p[i] + 1):
                    key = (i, k, t) if elig_aware else (i, t)
                    if key in self.forbid or (i, t) in self.forbid:
                        continue
                    if elig_aware:
                        self.idx[(i, k, t)] = len(self.cols)
                        self.cols.append((i, k, t))
                    else:
                        self.idx[(i, t)] = len(self.cols)
                        self.cols.append((i, t))
        self.N = len(self.cols)
        rows, hi = [], []
        # assignment
        for i in range(self.n):
            row = {}
            for key, c in self.idx.items():
                if key[0] == i:
                    row[c] = 1.0
            rows.append(row)
            hi.append(1.0)
        # capacity
        if elig_aware:
            for k in range(self.m):
                for t in range(T):
                    row = {}
                    for (i, kk, s), c in self.idx.items():
                        if kk == k and s <= t < s + self.p[i]:
                            row[c] = row.get(c, 0) + 1.0
                    rows.append(row)
                    hi.append(1.0)
        else:
            for t in range(T):
                row = {}
                for (i, s), c in self.idx.items():
                    if s <= t < s + self.p[i]:
                        row[c] = row.get(c, 0) + 1.0
                rows.append(row)
                hi.append(self.m)
        # expectation (optional)
        if use_expect:
            for i in range(self.n):
                for j in inst['succ'][i]:
                    row = {}
                    for key, c in self.idx.items():
                        a, t = key[0], key[-1]
                        if a == i:
                            row[c] = row.get(c, 0) + t
                        if a == j:
                            row[c] = row.get(c, 0) - t
                    rows.append(row)
                    hi.append(-self.p[i])
        # stochastic dominance
        if use_dom:
            last = [T - q[i] - self.p[i] for i in range(self.n)]
            for i in range(self.n):
                for j in inst['succ'][i]:
                    # F_i(t) >= F_j(t+p_i).  Outside this range the row is
                    # either 0 >= 0 or 1 >= something (trivially true).
                    tlo = max(0, est[j] - self.p[i])
                    thi = last[i] - 1
                    for t in range(tlo, thi + 1):
                        row = {}
                        for key, c in self.idx.items():
                            a, s = key[0], key[-1]
                            if a == i and s <= t:
                                row[c] = row.get(c, 0) - 1.0
                            if a == j and s <= t + self.p[i]:
                                row[c] = row.get(c, 0) + 1.0
                        if row:
                            rows.append(row)
                            hi.append(0.0)
        A = lil_matrix((len(rows), self.N))
        for r, row in enumerate(rows):
            for c, v in row.items():
                A[r, c] = v
        self.A = A.tocsr()
        self.hi = np.asarray(hi, dtype=float)
        self.n_eq = self.n

    def solve(self, bounds=None, time_limit=None):
        opts = {'method': 'highs'}
        if time_limit is not None:
            opts['time_limit'] = time_limit
        if bounds is None:
            bounds = (0, 1)
        return linprog(np.zeros(self.N), A_ub=self.A, b_ub=self.hi,
                       A_eq=self.A[:self.n_eq], b_eq=np.ones(self.n),
                       bounds=bounds, **opts)

    def root(self):
        return self.solve().status

    def integral_solution(self, z, tol=1e-7):
        s = [None] * self.n
        for c, key in enumerate(self.cols):
            if z[c] > 1.0 - tol:
                i, t = key[0], key[-1]
                if s[i] is not None:
                    return None
                s[i] = (t, key[1] if self.elig_aware else None)
        if any(x is None for x in s):
            return None
        return s


def sdecc_no(inst, h, nodecap=5000, stats=None, use_expect=False,
             use_dom=True, elig_aware=None):
    """Return (verdict, stats), verdict False=NO, True=YES, None=cap/unknown."""
    n = inst['n']
    if elig_aware is None:
        elig_aware = any(len(set(inst['elig'][i])) < inst['m']
                         for i in range(n))
    est, q = heads_tails(inst, 0, [0] * n)
    lp = SDLP(inst, h, est, q, use_expect=use_expect, use_dom=use_dom,
              elig_aware=elig_aware)
    st = {'lp_nodes': 0, 'root': None, 'depth': 0, 'nodes': 0, 'branches': []}
    base = [(0, 1)] * lp.N

    def dfs(bounds, depth):
        st['lp_nodes'] += 1
        if st['lp_nodes'] > nodecap:
            raise TimeoutError
        res = lp.solve(bounds)
        if st['lp_nodes'] == 1:
            st['root'] = ('infeasible' if res.status == 2 else
                          ('feasible' if res.status == 0 else 'other'))
        if res.status == 2:
            return False
        if res.status != 0:
            return None
        z = res.x
        frac = []
        for c, key in enumerate(lp.cols):
            if 1e-7 < z[c] < 1 - 1e-7:
                frac.append((abs(z[c] - 0.5), c, key[0], key[-1]))
        if not frac:
            st['depth'] = max(st['depth'], depth)
            return True
        frac.sort()
        _, c, i, t = frac[0]
        times = sorted(set(key[-1] for key in lp.idx if key[0] == i))
        s = 0.0
        mid = t
        for tt in times:
            if elig_aware:
                s += sum(z[lp.idx[(i, k, tt)]] for k in lp.elig[i])
            else:
                s += z[lp.idx[(i, tt)]]
            if s >= 0.5:
                mid = tt
                break
        if mid >= times[-1]:
            mid = times[-1] - 1
        st['branches'].append((i, mid, depth))
        lo = list(bounds)
        hi2 = list(bounds)
        if elig_aware:
            for tt in times:
                for k in lp.elig[i]:
                    cc = lp.idx[(i, k, tt)]
                    if tt > mid:
                        lo[cc] = (0, 0)
                    else:
                        hi2[cc] = (0, 0)
        else:
            for tt in times:
                cc = lp.idx[(i, tt)]
                if tt > mid:
                    lo[cc] = (0, 0)
                else:
                    hi2[cc] = (0, 0)
        r1 = dfs(lo, depth + 1)
        if r1 is not False:
            return r1
        r2 = dfs(hi2, depth + 1)
        if r2 is not False:
            return r2
        st['depth'] = max(st['depth'], depth)
        return False

    try:
        v = dfs(base, 0)
    except TimeoutError:
        v = None
    st['nodes'] = st['lp_nodes']
    if stats is not None:
        stats.update(st)
    return v, st
