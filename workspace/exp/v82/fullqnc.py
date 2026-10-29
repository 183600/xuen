import sys
sys.path[:0] = ['exp/v82', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from qnc import QNC
from fullsd import FullSD

class FullQNC(QNC):
    def __init__(self, inst, h, tie='col', **kw):
        super().__init__(inst, h, **kw)
        self.tie = tie
        self.lp = FullSD(inst, h, elig_aware=self.elig)

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
                elif self.tie == 'dom':
                    score = (abs(z[cc] - 0.5), self._effdom(i, bounds), cc)
                elif self.tie == 'domfirst':
                    score = (self._effdom(i, bounds), abs(z[cc] - 0.5), cc)
                elif self.tie == 'negdom':
                    score = (abs(z[cc] - 0.5), -self._effdom(i, bounds), cc)
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

from qnc import Budget
