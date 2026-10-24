"""v8.2 RACE-ALC: a distributed NO/YES budget race inside the fixed-h oracle.

The outer CRISP bracket is kept.  The inner CHD oracle is replaced by two
agents that share the root LP, the cuts and the clauses:

  * N-agent: the exact downward search (Farkas / quorum certificates);
  * Y-agent: deterministic cheap/hull LDS construction.

A geometric ladder gives each agent alternating budget slices.  The first
agent to return a certified answer stops the race.  On a NO instance this
avoids the Y-agent's long fruitless construction; on a YES instance it
avoids a long fruitless NO search.
"""
import sys
import time

sys.path[:0] = ['exp/v9b', 'exp/v9c', 'exp/v9d', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from chd import CHD
from rdf import check_schedule
from qnc import Budget


class RACE(CHD):
    def __init__(self, inst, h, race_lp=(8, 16, 32, 64, 80),
                 race_nodes=(64, 256, 1024, 4096, 5000),
                 yes_nodes=(128, 512, 2048, 4096, 60000), **kw):
        super().__init__(inst, h, **kw)
        self.race_lp = tuple(race_lp)
        self.race_nodes = tuple(race_nodes)
        self.yes_nodes_slice = tuple(yes_nodes)
        self.race_rounds = 0
        self.race_trace = []

    def _no_slice(self, lp_budget, node_budget):
        self.budget = min(lp_budget, self.per_query_lp_cap)
        self.nodecap = self.nodes + node_budget
        try:
            return self._search([(0, 1)] * self.lp.base.N, 0)
        except Budget:
            return None, 'budget-slice'
        except Exception:
            return None, 'exception-slice'

    def _yes_slice(self, node_budget):
        if self.root_z is None:
            return False
        # one cheap rank (mean) is enough for a slice; full portfolio later
        from chd import _lp_distribution, _mean_rank
        from rdf import _heads_latest
        est, qt, latest = _heads_latest(self.inst, self.h)
        dist = _lp_distribution(self, self.root_z)
        rk = _mean_rank(dist, est)
        rk = {i: rk[i] + i * 1e-9 for i in range(self.inst['n'])}
        got, nd, d = self._lds(rk, node_budget, self.cheap_disc,
                               lower={i: est[i] for i in range(self.inst['n'])},
                               upper={i: latest[i] for i in range(self.inst['n'])})
        self.lds_nodes += nd
        self.lds_calls += 1
        if got is not None and self._accept(got, 'race:mean', 'mean', d):
            return True
        return False

    def decide(self, budget=100000, nodecap=5000, max_rounds=60, topk=100):
        if not self.yes_scan:
            return super().decide(budget, nodecap, max_rounds, topk)
        self.per_query_lp_cap = budget
        n = self.inst['n']
        # round 0..: alternate N and Y slices
        for r, (lb, nb, yb) in enumerate(zip(self.race_lp, self.race_nodes,
                                            self.yes_nodes_slice)):
            self.race_rounds += 1
            t0 = time.time()
            v, why = self._no_slice(lb, nb)
            self.race_trace.append(('N', r, v, round(time.time() - t0, 3),
                                    self.lp_solves, self.nodes))
            if v is not None:
                self.phase = 'race-N'
                return v, self._stats('race-no-' + str(r))
            if self.root_z is None:
                res = self.lp.solve([(0, 1)] * self.lp.base.N)
                self.lp_solves += 1
                if res.status == 2:
                    self.phase = 'race-N'
                    return False, self._stats('race-root-no')
                if res.status == 0:
                    import numpy as np
                    self.root_z = np.array(res.x, copy=True)
            t0 = time.time()
            ok = self._yes_slice(yb)
            self.race_trace.append(('Y', r, ok, round(time.time() - t0, 3),
                                    self.lp_solves, self.nodes))
            if ok:
                self.phase = 'race-Y'
                return True, self._stats('race-yes-' + str(r))
            if self.lp_solves >= budget or self.nodes > self.nodecap:
                break
        # final: full NO (the old phase C), then full YES fallback
        self.budget = budget
        self.nodecap = self.nodes + nodecap
        try:
            v, why = self._search([(0, 1)] * self.lp.base.N, 0)
        except Budget:
            v, why = None, 'budget-final'
        if v is not None:
            self.phase = 'race-C'
            return v, self._stats('race-final-no')
        if self.root_z is not None and self._cheap_lds():
            self.phase = 'race-Y2'
            return True, self._stats('race-final-yes')
        self.phase = 'race-U'
        return None, self._stats('race-unknown')

    def _stats(self, why):
        st = super()._stats(why)
        st.update(race_rounds=self.race_rounds,
                  race_trace=list(self.race_trace))
        return st


class RACE2(RACE):
    """Race with a real cheap-LDS portfolio in the Y slices."""

    def __init__(self, inst, h, race_lp=(24, 48, 80),
                 race_nodes=(256, 1024, 5000),
                 yes_nodes=(2000, 5000, 60000), **kw):
        super().__init__(inst, h, race_lp=race_lp, race_nodes=race_nodes,
                         yes_nodes=yes_nodes, **kw)

    def _yes_slice(self, node_budget):
        if self.root_z is None:
            return False
        old_cap, old_tot = self.cheap_nodecap, self.cheap_nodes
        self.cheap_nodecap = max(64, node_budget // 4)
        self.cheap_nodes = node_budget
        try:
            return self._cheap_lds()
        finally:
            self.cheap_nodecap, self.cheap_nodes = old_cap, old_tot


class RACE3(CHD):
    """One cheap YES probe between two NO slices, then the CHD fallback.

    This is the smallest useful race: it targets the case where the NO
    proof needs slightly more than the phase-A budget while the YES
    constructor is very expensive.
    """

    def __init__(self, inst, h, extra_no_budget=20, extra_no_nodes=400,
                 probe_cap=2000, **kw):
        super().__init__(inst, h, **kw)
        self.extra_no_budget = extra_no_budget
        self.extra_no_nodes = extra_no_nodes
        self.probe_cap = probe_cap
        self.race_trace = []

    def _probe_yes(self, cap):
        old_cap, old_tot = self.cheap_nodecap, self.cheap_nodes
        self.cheap_nodecap = max(64, cap // 4)
        self.cheap_nodes = cap
        try:
            return self._cheap_lds()
        finally:
            self.cheap_nodecap, self.cheap_nodes = old_cap, old_tot

    def decide(self, budget=100000, nodecap=5000, max_rounds=60, topk=100):
        if not self.yes_scan:
            return super().decide(budget, nodecap, max_rounds, topk)
        # phase A (small NO)
        self.budget = min(budget, self.small_budget)
        self.nodecap = min(nodecap, self.small_nodes)
        try:
            v, why = self._search([(0, 1)] * self.lp.base.N, 0)
        except Budget:
            v, why = None, 'budget-small'
        self.race_trace.append(('A', v, self.lp_solves, self.nodes))
        if v is not None:
            self.phase = 'A'
            return v, self._stats(why)
        if self.root_z is None:
            res = self.lp.solve([(0, 1)] * self.lp.base.N)
            self.lp_solves += 1
            if res.status == 2:
                self.phase = 'A'
                return False, self._stats('root-core')
            if res.status == 0:
                import numpy as np
                self.root_z = np.array(res.x, copy=True)
        # cheap YES probe
        if self.root_z is not None:
            if self._probe_yes(self.probe_cap):
                self.phase = 'race-Y'
                return True, self._stats('race-yes-probe')
        # extra NO slice
        self.budget = min(budget, self.extra_no_budget)
        self.nodecap = self.nodes + self.extra_no_nodes
        try:
            v, why = self._search([(0, 1)] * self.lp.base.N, 0)
        except Budget:
            v, why = None, 'budget-extra'
        self.race_trace.append(('N2', v, self.lp_solves, self.nodes))
        if v is not None:
            self.phase = 'race-N'
            return v, self._stats('race-no-extra')
        # fallback: hull, random off, full NO (copy of CHD.decide)
        if self.root_z is not None and self.hull_on:
            self.budget = max(self.lp_solves + self.inst['n'], budget)
            if self._hull_lds():
                self.phase = 'race-hull'
                return True, self._stats('race-yes-hull')
        self.budget = budget
        self.nodecap = self.nodes + nodecap
        try:
            v, why = self._search([(0, 1)] * self.lp.base.N, 0)
        except Budget:
            v, why = None, 'budget'
        self.phase = 'C'
        return v, self._stats(why)

    def _stats(self, why):
        st = super()._stats(why)
        st.update(race_trace=list(self.race_trace))
        return st
