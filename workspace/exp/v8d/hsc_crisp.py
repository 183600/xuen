"""HSC-ALC outer wrapper: CRISP bracket with the canonical LDS oracle.

The only changes relative to exp/v8c/chip.py are on the YES side:
  * the inner oracle is HSC instead of CHD;
  * the randomized full-DFS fallback is disabled.  On the certified
    corpus the deterministic cheap+hull LDS already closes every YES, so
    the fallback only burns nodes on NO instances (one stress case spent
    60k nodes there).  If the deterministic phase cannot find a schedule,
    the oracle returns UNKNOWN and phase C decides; it never guesses.
"""
import sys

sys.path[:0] = ['exp/v8d', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from chip import CRISP, chip_bounds
from hsc import HSC


class HSCRISP(CRISP):
    def _decide(self, h):
        rdf = HSC(self.inst, h, yes_scan=True, cheap_disc=2,
                  hull_disc=4, hull_on=True, random_fallback=False)
        try:
            v, st = rdf.decide(budget=self.per_query_lp,
                               nodecap=self.per_query_nodes)
        except Exception:
            v, st = None, rdf._stats('exception')
        self.last_oracle = rdf
        return v, st, rdf
