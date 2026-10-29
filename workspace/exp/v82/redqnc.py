import sys
sys.path[:0] = ['exp/v82', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from scipy.optimize import linprog
import numpy as np
from lazy import LazySD
from qnc import QNC, Budget

class ReducedSD(LazySD):
    def __init__(self, inst, h, rows, **kw):
        super().__init__(inst, h, **kw)
        self.cuts = [tuple(r) for r in rows]
        self.cutset = set(self.cuts)
        self._rowcache = {}
    def _row(self, i, j, t):
        key = (i, j, t)
        r = self._rowcache.get(key)
        if r is None:
            r = super()._row(i, j, t)
            self._rowcache[key] = r
        return r

class RedQNC(QNC):
    def __init__(self, inst, h, rows, tie='col', **kw):
        super().__init__(inst, h, **kw)
        self.tie = tie
        self.lp = ReducedSD(inst, h, rows, elig_aware=self.elig)
    def _effdom(self, i, bounds):
        c = 0
        for t in self.domain(i):
            if self.elig:
                for k in self.lp.base.elig[i]:
                    key = (i, k, t)
                    if key in self.lp.idx and bounds[self.lp.idx[key]] != (0, 0):
                        c += 1; break
            else:
                key = (i, t)
                if key in self.lp.idx and bounds[self.lp.idx[key]] != (0, 0):
                    c += 1
        return c
    def _branch(self, bounds, depth, nodecap, max_rounds, topk):
        bounds, _ = self._apply_force(bounds)
        i0 = self._empty_job(bounds) if self.use_empty else None
        if i0 is not None:
            self.empty_prunes += 1
            return False, 'empty'
        F = self._forbids(bounds)
        for E in self.clauses:
            if E <= F:
                self.prunes += 1
                return False, 'clause'
        self.nodes += 1
        if self.nodes > nodecap:
            raise Budget
        res, z = self._solve(bounds, max_rounds, topk)
        if res.status == 2:
            self._learn(F)
            return False, 'no'
        if z is None:
            return None, 'roundcap'
        frac = []
        for cc, key in enumerate(self.lp.cols):
            if 1e-7 < z[cc] < 1 - 1e-7:
                i = key[0]
                if self.tie == 'col':
                    score = (abs(z[cc] - 0.5), cc)
                else:
                    score = (abs(z[cc] - 0.5), cc)
                frac.append((score, cc, i, key[-1]))
        if not frac:
            return True, 'yes'
        frac.sort()
        _, cc, i, t = frac[0]
        times = sorted(self.domain(i))
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
        lo = list(bounds)
        hi2 = list(bounds)
        for tt in times:
            if self.elig:
                for k in self.lp.base.elig[i]:
                    if (i, k, tt) in self.lp.idx:
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
        a, why = self._branch(lo, depth + 1, nodecap, max_rounds, topk)
        if a is not False:
            return a, why
        return self._branch(hi2, depth + 1, nodecap, max_rounds, topk)

class CachedReducedSD(ReducedSD):
    def __init__(self, inst, h, rows, **kw):
        super().__init__(inst, h, rows, **kw)
        self._A, self._hi = self.matrix()
    def solve(self, bounds=None):
        return linprog(np.zeros(self.base.N), A_ub=self._A, b_ub=self._hi,
                       A_eq=self._A[:self.n_eq], b_eq=np.ones(self.n),
                       bounds=bounds or (0, 1), method='highs')

class CachedRedQNC(RedQNC):
    def __init__(self, inst, h, rows, **kw):
        super().__init__(inst, h, rows, **kw)
        self.lp = CachedReducedSD(inst, h, rows, elig_aware=self.elig)
