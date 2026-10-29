"""HSC + cut pool: the v8.2 algorithm.

Two hash tables share work across the h-search space:
  * CUT: lazy dominance cuts (i,j,t), valid for every h, reused by every
    oracle call of the bracket;
  * STATE: canonical partial-schedule states in the LDS constructor,
    with a budget-aware failure table and machine-symmetry canonical keys.
The randomized full-DFS fallback is removed from the deterministic path.
"""
import sys

sys.path[:0] = ['exp/v8d', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from hsc_crisp import HSCRISP
from hsc import HSC


class HSCPool(HSCRISP):
    def initial_bounds(self):
        self.cut_pool = set()
        return super().initial_bounds()

    def _decide(self, h):
        rdf = HSC(self.inst, h, yes_scan=True, cheap_disc=2,
                  hull_disc=4, hull_on=True, random_fallback=False)
        rdf.lp.cuts = list(self.cut_pool)
        rdf.lp.cutset = set(self.cut_pool)
        try:
            v, st = rdf.decide(budget=self.per_query_lp,
                               nodecap=self.per_query_nodes)
        except Exception:
            v, st = None, rdf._stats('exception')
        self.cut_pool |= rdf.lp.cutset
        self.last_oracle = rdf
        return v, st, rdf
