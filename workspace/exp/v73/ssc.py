"""v7.3 SSC-ALC: solution-space cover with a witness pool.

QNC/v8.0 style cover LP, but the clause family is kept as a subsumption
antichain and every feasible cover point is fed back into the primal
witness pool.  The cover LP is only solved when no known feasible point
hits the whole clause family; otherwise tau >= 1 is already witnessed and
the probe is provably useless.
"""
import sys, time
sys.path[:0] = ['exp/v80', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
import numpy as np
from qcm import QCM, Proved, cover_lp, cols_of
from qnc import QNC, Budget


class SSC(QCM):
    def __init__(self, inst, h, **kw):
        super().__init__(inst, h, **kw)
        self.subsumed = 0
        self.cover_witness = 0

    @staticmethod
    def _d(E):
        d = {}
        for (i, t) in E:
            d.setdefault(i, set()).add(t)
        return {i: frozenset(S) for i, S in d.items()}

    def _subsumes(self, A, B):
        A, B = self._d(A), self._d(B)
        if not set(A) <= set(B):
            return False
        return all(A[i] <= B[i] for i in A)

    def _add_antichain(self, E):
        E = frozenset(E)
        for A in self.clauses:
            if self._subsumes(A, E):
                if A == E:
                    return True          # already inserted by QNC._learn
                self.subsumed += 1
                return False
        keep = []
        for A in self.clauses:
            if self._subsumes(E, A):
                self.subsumed += 1
            else:
                keep.append(A)
        keep.append(E)
        self.clauses[:] = keep
        return True

    def _learn(self, F):
        # QNC._learn: append leaf, add clause, force
        r = QNC._learn(self, F)
        cert, E = r
        if cert is None or E is None:
            return r
        if not E:
            self.stopped = True
            raise Proved
        if not self._add_antichain(E):
            return r
        if not self._should_probe():
            return r
        if self.pool and self._pool_hits_all():
            self.skipped += 1
            return r
        t0 = time.time()
        tau, res = cover_lp(self.lp, self.clauses)
        self.cover_t += time.time() - t0
        self.cover_lp += 1
        self.probes.append((len(self.clauses),
                            None if tau is None else float(tau),
                            self.lp_solves, self.nodes))
        if res is not None and res.status == 0:
            z = np.asarray(res.x[:self.lp.N])
            if len(self.pool) < 128:
                self.pool.append(z)
            self.cover_witness += 1
        if tau is not None and tau < 1.0 - self.eps - 1e-9:
            self.mix = (list(self.clauses), float(tau), res)
            self.stopped = True
            raise Proved
        return r

    def _stats(self, why):
        st = super()._stats(why)
        st.update(subsumed=self.subsumed, cover_witness=self.cover_witness)
        return st
