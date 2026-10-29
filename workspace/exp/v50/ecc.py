"""ECC: start-time LP / cut-packing certificate probe (v5.0).

Primal:
  z[i,t] = 1 iff job i starts at t (relaxed to [0,1])
  sum_t z[i,t] = 1
  sum_i sum_{s<=t<s+p_i} z[i,s] <= m          (time capacity)
  sum_t t z[i,t] + p_i <= sum_t t z[j,t]      (i -> j precedence)
The LP is a relaxation of nonpreemptive feasibility.  Its dual is a
fractional packing of time cuts and precedence cuts (a cut-packing LP;
without the precedence rows it reduces to the Horn/EPC min-cut).
"""
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import lil_matrix

try:
    from po import heads_tails
except Exception:
    import po
    heads_tails = po.heads_tails


class StartLP:
    def __init__(self, inst, T, est=None, q=None, use_prec=True, use_cap=True):
        self.inst = inst
        self.T = T
        self.n = inst['n']
        self.m = inst['m']
        self.p = inst['p']
        self.use_prec = use_prec
        self.use_cap = use_cap
        if est is None or q is None:
            est, q = heads_tails(inst, 0, [0] * self.n)
        self.est, self.q = est, q
        self.idx = {}
        self.cols = []
        for i in range(self.n):
            for t in range(est[i], T - q[i] - self.p[i] + 1):
                self.idx[(i, t)] = len(self.cols)
                self.cols.append((i, t))
        self.N = len(self.cols)
        rows, lo, hi = [], [], []
        for i in range(self.n):
            row = {c: 1 for (a, t), c in self.idx.items() if a == i}
            rows.append(row); lo.append(1); hi.append(1)
        if use_cap:
            for t in range(T):
                row = {}
                for (i, s), c in self.idx.items():
                    if s <= t < s + self.p[i]:
                        row[c] = row.get(c, 0) + 1
                rows.append(row); lo.append(-np.inf); hi.append(self.m)
        if use_prec:
            for i in range(self.n):
                for j in inst['succ'][i]:
                    row = {}
                    for (a, t), c in self.idx.items():
                        if a == i:
                            row[c] = row.get(c, 0) + t
                        if a == j:
                            row[c] = row.get(c, 0) - t
                    rows.append(row); lo.append(-np.inf); hi.append(-self.p[i])
        A = lil_matrix((len(rows), self.N))
        for r, row in enumerate(rows):
            for c, v in row.items():
                A[r, c] = v
        self.A = A.tocsr()
        self.lo = np.array(lo)
        self.hi = np.array(hi)
        self.n_eq = self.n

    def solve(self, bounds=None):
        if bounds is None:
            bounds = (0, 1)
        return linprog(np.zeros(self.N), A_ub=self.A, b_ub=self.hi,
                       A_eq=self.A[:self.n_eq], b_eq=self.lo[:self.n_eq],
                       bounds=bounds, method='highs')

    def root(self):
        res = self.solve()
        return res.status


def ecc_no(inst, h, nodecap=20000, stats=None):
    """Return (verdict, stats) with verdict in {False, True, None}.

    False = proved NO; True = found a feasible integral start assignment;
    None = node cap.  False is sound.
    """
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    lp = StartLP(inst, h, est, q)
    st = {'lp_nodes': 0, 'lp_solves': 0, 'root': None, 'depth': 0}
    base = [(0, 1)] * lp.N

    def dfs(bounds, depth):
        st['lp_nodes'] += 1
        if st['lp_nodes'] > nodecap:
            raise TimeoutError
        st['lp_solves'] += 1
        res = lp.solve(bounds)
        if res.status == 2:
            return False
        if res.status != 0:
            return None
        z = res.x
        frac = []
        for c, (i, t) in enumerate(lp.cols):
            if 1e-7 < z[c] < 1 - 1e-7:
                frac.append((abs(z[c] - 0.5), c, i, t))
        if not frac:
            st['depth'] = max(st['depth'], depth)
            return True
        frac.sort()
        _, c, i, t = frac[0]
        times = sorted(tt for (a, tt), cc in lp.idx.items() if a == i)
        s = 0.0
        mid = t
        for tt in times:
            s += z[lp.idx[(i, tt)]]
            if s >= 0.5:
                mid = tt
                break
        hi_lo = list(bounds)
        hi_hi = list(bounds)
        for tt in times:
            cc = lp.idx[(i, tt)]
            if tt > mid:
                hi_lo[cc] = (0, 0)
            else:
                hi_hi[cc] = (0, 0)
        r1 = dfs(hi_lo, depth + 1)
        if r1 is not False:
            return r1
        r2 = dfs(hi_hi, depth + 1)
        if r2 is not False:
            return r2
        st['depth'] = max(st['depth'], depth)
        return False

    try:
        v = dfs(base, 0)
    except TimeoutError:
        v = None
    st['root'] = 'infeasible' if lp.root() == 2 else ('feasible' if lp.root() == 0 else 'other')
    if stats is not None:
        stats.update(st)
    return v, st


class StartLPElig:
    """Eligibility-aware start-time LP: z[i,k,t] for k in elig(i)."""
    def __init__(self, inst, T, est=None, q=None, use_prec=True, use_cap=True):
        self.inst = inst
        self.T = T
        self.n = inst['n']
        self.m = inst['m']
        self.p = inst['p']
        self.elig = [sorted(set(e)) for e in inst['elig']]
        if est is None or q is None:
            est, q = heads_tails(inst, 0, [0] * self.n)
        self.est, self.q = est, q
        self.idx = {}
        self.cols = []
        for i in range(self.n):
            for k in self.elig[i]:
                for t in range(est[i], T - q[i] - self.p[i] + 1):
                    self.idx[(i, k, t)] = len(self.cols)
                    self.cols.append((i, k, t))
        self.N = len(self.cols)
        rows, lo, hi = [], [], []
        for i in range(self.n):
            row = {c: 1 for (a, k, t), c in self.idx.items() if a == i}
            rows.append(row); lo.append(1); hi.append(1)
        if use_cap:
            for k in range(self.m):
                for t in range(T):
                    row = {}
                    for (i, kk, s), c in self.idx.items():
                        if kk == k and s <= t < s + self.p[i]:
                            row[c] = row.get(c, 0) + 1
                    rows.append(row); lo.append(-np.inf); hi.append(1)
        if use_prec:
            for i in range(self.n):
                for j in inst['succ'][i]:
                    row = {}
                    for (a, k, t), c in self.idx.items():
                        if a == i:
                            row[c] = row.get(c, 0) + t
                        if a == j:
                            row[c] = row.get(c, 0) - t
                    rows.append(row); lo.append(-np.inf); hi.append(-self.p[i])
        A = lil_matrix((len(rows), self.N))
        for r, row in enumerate(rows):
            for c, v in row.items():
                A[r, c] = v
        self.A = A.tocsr()
        self.lo = np.array(lo)
        self.hi = np.array(hi)
        self.n_eq = self.n

    def solve(self, bounds=None):
        if bounds is None:
            bounds = (0, 1)
        return linprog(np.zeros(self.N), A_ub=self.A, b_ub=self.hi,
                       A_eq=self.A[:self.n_eq], b_eq=self.lo[:self.n_eq],
                       bounds=bounds, method='highs')

    def root(self):
        return self.solve().status
