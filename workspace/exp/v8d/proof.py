"""v8.2 PACE: proof-only finalization for the CRISP bracket.

The last call in CABOpt.optimize is always a NO proof at opt-1.  There is
no reason to run the YES constructor there: if opt is correct the answer
is NO, and if it is not, a pure NO search can only fail to certify (it
cannot return a false NO).  This module adds that distinction.
"""
import sys
sys.path[:0] = ['exp/v8d', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from cab import CABOpt
from chip import CRISP
from chd import CHD
from race import RACE


class ProofCRISP(CRISP):
    def __init__(self, *a, oracle='chd', **kw):
        self.oracle = oracle
        super().__init__(*a, **kw)

    def _decide(self, h, proof_only=False, budget=None, nodecap=None):
        budget = self.per_query_lp if budget is None else budget
        nodecap = self.per_query_nodes if nodecap is None else nodecap
        if self.oracle == 'chd':
            rdf = CHD(self.inst, h, yes_scan=not proof_only,
                      cheap_disc=2, hull_disc=4, hull_on=True)
        elif self.oracle == 'race':
            rdf = RACE(self.inst, h, yes_scan=not proof_only,
                       cheap_disc=2, hull_disc=4, hull_on=True)
        else:
            raise ValueError(self.oracle)
        try:
            v, st = rdf.decide(budget=budget, nodecap=nodecap)
        except Exception:
            v, st = None, rdf._stats('exception')
        self.last_oracle = rdf
        return v, st, rdf

    def optimize(self):
        lb, ub, starts, machs = self.initial_bounds()
        self.lb0, self.ub0 = lb, ub
        self.lb = lb
        if ub is not None:
            self.schedule, self.machine, self.opt = starts, machs, ub
        while self.lb < self.opt and self.queries < self.max_queries:
            h = (self.lb + self.opt) // 2
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
            v, st, rdf = self._decide(self.opt - 1, proof_only=True)
            self.queries += 1
            self._absorb(st)
            self._record(self.opt - 1, v, st)
            if v is False:
                self.no_states[self.opt - 1] = rdf
                self.lb_proof = rdf
            else:
                self.certified = False
        return self._result()


class ProofOnlyFinal(ProofCRISP):
    pass
