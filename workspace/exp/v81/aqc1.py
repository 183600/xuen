"""AQC with single-atom probing (no forced pair probe)."""
import sys
sys.path[:0]=['exp/v81','exp/v71','exp/v61','exp/v60','exp/v13']
from aqc import AQC
from qcc import Closed


class AQC1(AQC):
    def __init__(self, inst, h, **kw):
        super().__init__(inst, h, **kw)
        self.pair_on = False

    def _probe_root(self, z):
        if (not self.probe_on or self.probe_off or self.probes >= self.probe_cap):
            return None
        for _, _, i, atoms in self._rank_jobs(z)[:self.probe_jobs]:
            mass, t = atoms[0]
            ok, cert, Ep = self._probe_delete({(i, t)})
            if not ok:
                if self.probe_gate:
                    self.probe_off = True
                return None
            if len(Ep) != 1:
                return None
            st = self._learn_probe(Ep, cert)
            self.probe_units.append((i, t))
            if st == 'empty':
                raise Closed
            self.restarts += 1
            self._check_root()
            return 'unit'
        return None
