"""Lazy SD-ECC: cutting-plane separation of dominance rows + start branching.

Instead of materialising all O(|E|T) dominance rows, start from the
capacity-only LP and add only violated dominance cuts.  Separation is a
one-pass sweep over time (prefix sums of the start mass), i.e. a streaming
oracle.  Every added row is a valid inequality, so infeasibility of the
current subset already proves NO.
"""
import sys
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import lil_matrix

sys.path[:0] = ['exp/v60', 'exp/v13']
from sdecc import SDLP
from po import heads_tails


class LazySD:
    def __init__(self, inst, h, use_expect=False, elig_aware=False):
        self.base = SDLP(inst, h, use_expect=use_expect, use_dom=False,
                         elig_aware=elig_aware)
        self.inst = inst
        self.h = h
        self.n = inst['n']
        self.p = inst['p']
        self.elig_aware = elig_aware
        self.est, self.q = self.base.est, self.base.q
        self.idx = self.base.idx
        self.cols = self.base.cols
        self.n_eq = self.base.n_eq
        self.N = self.base.N
        self.baseA = self.base.A
        self.basehi = self.base.hi
        self.cuts = []          # (i,j,t)
        self.cutset = set()

    def _row(self, i, j, t):
        row = {}
        for key, c in self.idx.items():
            a, s = key[0], key[-1]
            if a == i and s <= t:
                row[c] = row.get(c, 0) - 1.0
            if a == j and s <= t + self.p[i]:
                row[c] = row.get(c, 0) + 1.0
        return row

    def matrix(self):
        nr = self.baseA.shape[0] + len(self.cuts)
        A = lil_matrix((nr, self.base.N))
        A[:self.baseA.shape[0], :] = self.baseA
        for r, (i, j, t) in enumerate(self.cuts, start=self.baseA.shape[0]):
            for c, v in self._row(i, j, t).items():
                A[r, c] = v
        hi = np.concatenate([self.basehi, np.zeros(len(self.cuts))])
        return A.tocsr(), hi

    def solve(self, bounds=None):
        A, hi = self.matrix()
        return linprog(np.zeros(self.base.N), A_ub=A, b_ub=hi,
                       A_eq=A[:self.n_eq], b_eq=np.ones(self.n),
                       bounds=bounds or (0, 1), method='highs')

    def separate(self, z, tol=1e-7, topk=100):
        # prefix start mass F[i][t]
        F = []
        for i in range(self.n):
            fi = np.zeros(self.h + 1)
            run = 0.0
            for t in range(self.h + 1):
                if self.elig_aware:
                    run += sum(z[self.idx[(i, k, t)]]
                               for k in self.base.elig[i]
                               if (i, k, t) in self.idx)
                else:
                    if (i, t) in self.idx:
                        run += z[self.idx[(i, t)]]
                fi[t] = run
            F.append(fi)
        viol = []
        last = [self.h - self.q[i] - self.p[i] for i in range(self.n)]
        for i in range(self.n):
            for j in self.inst['succ'][i]:
                tlo = max(0, self.est[j] - self.p[i])
                for t in range(tlo, last[i]):
                    v = F[j][min(t + self.p[i], self.h)] - F[i][t]
                    if v > tol:
                        viol.append((v, i, j, t))
        viol.sort(reverse=True)
        return viol[:topk]

    def solve_node(self, bounds, max_rounds=30, topk=100, tol=1e-7):
        added = 0
        res = None
        for rnd in range(max_rounds):
            res = self.solve(bounds)
            if res.status != 0:
                return res, None, added, rnd
            v = self.separate(res.x, tol=tol, topk=topk)
            if not v:
                return res, res.x, added, rnd
            for _, i, j, t in v:
                if (i, j, t) not in self.cutset:
                    self.cutset.add((i, j, t))
                    self.cuts.append((i, j, t))
                    added += 1
        return res, (res.x if res.status == 0 else None), added, max_rounds


def lazy_no(inst, h, nodecap=5000, use_expect=False, elig_aware=None,
            stats=None):
    n = inst['n']
    if elig_aware is None:
        elig_aware = any(len(set(inst['elig'][i])) < inst['m']
                         for i in range(n))
    lp = LazySD(inst, h, use_expect=use_expect, elig_aware=elig_aware)
    st = {'lp_nodes': 0, 'root': None, 'cuts_added': 0, 'rounds': 0,
          'branches': [], 'nodes': 0}
    base = [(0, 1)] * lp.base.N

    def dfs(bounds, depth):
        st['lp_nodes'] += 1
        if st['lp_nodes'] > nodecap:
            raise TimeoutError
        res, z, added, rnd = lp.solve_node(bounds)
        st['cuts_added'] += added
        st['rounds'] += rnd + 1
        if st['lp_nodes'] == 1:
            st['root'] = ('infeasible' if res.status == 2 else
                          ('feasible' if res.status == 0 else 'other'))
        if res.status == 2:
            return False
        if z is None:
            return None
        frac = []
        for c, key in enumerate(lp.cols):
            if 1e-7 < z[c] < 1 - 1e-7:
                frac.append((abs(z[c] - 0.5), c, key[0], key[-1]))
        if not frac:
            return True
        frac.sort()
        _, c, i, t = frac[0]
        times = sorted(set(key[-1] for key in lp.idx if key[0] == i))
        s = 0.0
        mid = t
        for tt in times:
            if elig_aware:
                s += sum(z[lp.idx[(i, k, tt)]] for k in lp.base.elig[i]
                         if (i, k, tt) in lp.idx)
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
                for k in lp.base.elig[i]:
                    if (i, k, tt) not in lp.idx:
                        continue
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
        return dfs(hi2, depth + 1)

    try:
        v = dfs(base, 0)
    except TimeoutError:
        v = None
    st['nodes'] = st['lp_nodes']
    if stats is not None:
        stats.update(st)
    return v, st
