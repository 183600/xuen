"""Cut-pool variant: share h-independent lazy dominance cuts across oracle
calls of the CRISP bracket.

Every LazySD cut (i,j,t) is a valid dominance inequality for the original
scheduling polytope, independent of the deadline h.  The row is rebuilt on
the current time-indexed columns, so installing a cut learned at another h
is sound; it can only strengthen the LP.  The pool is a hash set keyed by
(i,j,t).
"""
import sys

sys.path[:0] = ['exp/v8d', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from chip import CRISP
from chd import CHD


class PoolCRISP(CRISP):
    def initial_bounds(self):
        self.cut_pool = set()
        self.pool_hits = 0
        return super().initial_bounds()

    def _decide(self, h):
        rdf = CHD(self.inst, h, yes_scan=True, cheap_disc=2,
                  hull_disc=4, hull_on=True)
        before = len(self.cut_pool)
        rdf.lp.cuts = list(self.cut_pool)
        rdf.lp.cutset = set(self.cut_pool)
        try:
            v, st = rdf.decide(budget=self.per_query_lp,
                               nodecap=self.per_query_nodes)
        except Exception:
            v, st = None, rdf._stats('exception')
        self.cut_pool |= rdf.lp.cutset
        self.pool_hits += before
        self.last_oracle = rdf
        return v, st, rdf
