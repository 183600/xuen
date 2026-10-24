"""Hybrid bracket: binary search, but when the bracket is narrow probe UB-1
first so that the mandatory NO proof at the eventual OPT-1 is often the
first query (and its cuts seed the pool for any later query)."""
import sys

sys.path[:0] = ['exp/v8d', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from hsc_pool import HSCPool


class HybridCRISP(HSCPool):
    def optimize(self):
        lb, ub, starts, machs = self.initial_bounds()
        self.lb0, self.ub0 = lb, ub
        self.lb = lb
        if ub is not None:
            self.schedule, self.machine, self.opt = starts, machs, ub
        while self.lb < self.opt and self.queries < self.max_queries:
            w = self.opt - self.lb
            h = self.opt - 1 if w <= 3 else (self.lb + self.opt) // 2
            v, st, rdf = self._decide(h)
            self.queries += 1
            self._absorb(st)
            self._record(h, v, st)
            if v is True:
                cmax = max(rdf.schedule[i] + self.inst['p'][i]
                           for i in range(self.inst['n']))
                if cmax < self.opt:
                    self.opt = cmax
                    self.schedule = list(rdf.schedule)
                    self.machine = list(rdf.machine)
            elif v is False:
                self.lb = max(self.lb, h + 1)
                self.no_states[h] = rdf
                self.lb_proof = rdf
            else:
                self.unknown += 1
                self._recover_unknown(h)
        self.certified = (self.lb == self.opt and self.opt is not None)
        if self.certified and (self.opt - 1) not in self.no_states:
            v, st, rdf = self._decide(self.opt - 1)
            self.queries += 1
            self._absorb(st)
            self._record(self.opt - 1, v, st)
            if v is False:
                self.no_states[self.opt - 1] = rdf
                self.lb_proof = rdf
            else:
                self.certified = False
        return self._result()
