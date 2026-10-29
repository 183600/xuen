import sys, time
sys.path[:0] = ['exp/v82', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from lazy import LazySD

class FullSD(LazySD):
    def __init__(self, inst, h, **kw):
        super().__init__(inst, h, **kw)
        self._rowcache = {}
        last = [h - self.q[i] - self.p[i] for i in range(self.n)]
        for i in range(self.n):
            for j in inst['succ'][i]:
                tlo = max(0, self.est[j] - self.p[i])
                for t in range(tlo, last[i]):
                    key = (i, j, t)
                    if key not in self.cutset:
                        self.cutset.add(key); self.cuts.append(key)
    def _row(self, i, j, t):
        key = (i, j, t)
        r = self._rowcache.get(key)
        if r is None:
            r = super()._row(i, j, t)
            self._rowcache[key] = r
        return r
