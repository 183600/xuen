"""v7.5 QLC-ALC: quorum-loss-compiled ALC.

This round keeps the v7.1 QNC state (Farkas leaves, essential scopes,
quorum clauses, force, zero-LP empty-domain precheck) and the v7.3
cover test (a family of quorum clauses is compiled into one global
cover LP).  The new ingredient is the branching rule.

At a fractional LP solution z, for each job i let

    z_it = sum_{k eligible for i} z_{i,k,t}
    A_i(z) = sum_t min(z_it, 1 - z_it)          (ambiguity loss)

A_i is the L1 distance from job i's start distribution to an integral
one.  QNC/v7.3 branch on the single most fractional *atom*; QLC branches
on the job with the largest *total* ambiguity and splits at the mass
median of that job.  The split is the minimax partition of the job's
fractional mass:

    m* = min { m : sum_{t <= m} z_it >= 1/2 }.

The branch policy is deterministic and is compiled once in
`_ambiguity_split`; no runtime tuning or randomness is used.

Everything else is inherited from QCC: clause subsumption, unit
propagation, case branching, the cover LP, force and audit.  The cover
LP is the "compiler" layer: individual theory lemmas are linked into a
single multi-certificate refutation instead of being tested one by one.
"""
import sys
import collections

sys.path[:0] = ['exp/v73', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from qcc import QCC


class QLC(QCC):
    def __init__(self, inst, h, split='mass_median', **kw):
        super().__init__(inst, h, **kw)
        self.split = split
        self.loss_events = 0
        self.loss_margin = 0.0
        self.loss_jobs = 0
        self.split_median = 0
        self.split_atom = 0

    # ------------------------------------------------------------- loss
    def _start_mass(self, dom, z):
        mass = collections.defaultdict(float)
        for cc, key in enumerate(self.lp.cols):
            i, t = key[0], key[-1]
            if t in dom[i]:
                mass[(i, t)] += float(z[cc])
        return mass

    def _ambiguity_split(self, dom, z):
        mass = self._start_mass(dom, z)
        frac = {}
        for i in sorted(dom):
            atoms = [(t, mass.get((i, t), 0.0)) for t in sorted(dom[i])]
            atoms = [(t, m) for t, m in atoms if 1e-7 < m < 1 - 1e-7]
            if atoms:
                frac[i] = atoms
        if not frac:
            return None

        def amb(i):
            return sum(min(m, 1.0 - m) for _, m in frac[i])

        scores = sorted(((amb(i), -i, i) for i in frac), reverse=True)
        i = scores[0][2]
        self.loss_events += 1
        if len(scores) > 1:
            self.loss_margin += scores[0][0] - scores[1][0]
        self.loss_jobs += 1

        times = sorted(dom[i])
        weights = [mass.get((i, t), 0.0) for t in times]
        total = sum(weights)
        if total <= 0:
            return None

        if self.split == 'largest_atom':
            k = max(range(len(times)), key=lambda r: weights[r])
            mid = times[k]
            self.split_atom += 1
        else:
            run = 0.0
            mid = times[0]
            for t, w in zip(times, weights):
                run += w
                if run >= 0.5 * total:
                    mid = t
                    break
            self.split_median += 1

        if mid >= times[-1]:
            mid = times[-1] - 1
        if mid < times[0]:
            mid = times[0]
        if mid >= times[-1]:
            return None

        A = frozenset(t for t in times if t <= mid)
        B = frozenset(t for t in times if t > mid)
        if not A or not B:
            return None
        return i, A, B

    def _median_split(self, dom, z):
        return self._ambiguity_split(dom, z)

    def _stats(self, why):
        st = super()._stats(why)
        st.update(loss_events=self.loss_events,
                  loss_margin=self.loss_margin,
                  split_median=self.split_median,
                  split_atom=self.split_atom)
        return st
