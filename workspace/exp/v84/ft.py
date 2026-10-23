"""Fault-tolerant QRC: lost leaf certificates trigger certified re-splitting.

The ordinary QRC marks a node NO as soon as its LP is infeasible, even if
the integer Farkas extraction failed.  That is sound for the *verdict* but
leaves the proof incomplete.  FTQRC treats a missing certificate as a
fail-stop event: the node is split on a domain, and both children (still
infeasible) are searched until leaves with verified certificates are
found.  The final decision is therefore backed by replayable leaves even
under a burst of extraction failures.
"""
import sys
sys.path[:0] = ['exp/v84', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from qrc import QRC
from cert import verify


class FTQRC(QRC):
    def __init__(self, inst, h, fail_calls=0, corrupt_calls=0, **kw):
        super().__init__(inst, h, **kw)
        self.heal_on_missing = True
        self.fail_left = fail_calls
        self.corrupt_left = corrupt_calls
        self.forced_fail = 0
        self.corrupted = 0

    def _analyse(self, F):
        if self.fail_left > 0:
            self.fail_left -= 1
            self.forced_fail += 1
            self.cert_fail += 1
            return None
        got = super()._analyse(F)
        if got is not None and self.corrupt_left > 0:
            self.corrupt_left -= 1
            self.corrupted += 1
            cert, E = got
            bad = dict(cert)
            bad['alpha'] = list(cert['alpha'])
            bad['alpha'][0] = bad['alpha'][0] + 1
            if not verify(self.inst, self.h, bad, forbid=E,
                          elig_aware=self.elig):
                self.cert_fail += 1
                return None
            return bad, E
        return got

    def _stats(self, why):
        st = super()._stats(why)
        st.update(forced_fail=self.forced_fail, corrupted=self.corrupted,
                  heals=self.heals)
        return st
