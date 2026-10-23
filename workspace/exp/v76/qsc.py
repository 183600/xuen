"""v7.3 QSC-ALC: quorum singleton scan + support-mining closure.

QSC keeps the v7.2 root fast path (span-first singleton probes, unit
traps) and adds the v7.3 support-mining operator as a fallback at every
fractional node:

    delete the support S_i(z) of one job
      -> if infeasible, extract the essential scope E of the Farkas dual
      -> if E is single-job, shrink that job's global domain to E_i
         (a *set* force, not only a singleton force)
      -> re-solve the node (force recursion / closure)

The root scan is tried first because on the seven known root traps it
closes in two probes.  If it finds no trap, mining can still discover a
proper multi-point quorum that singleton probing cannot see: if
LP(C,{t}) is feasible for every t in E but LP(C,E) is infeasible, only
the set probe refutes.  The final NO proof is either the two singleton
certificates of v7.2, a QNC leaf certificate, or two disjoint set-force
certificates; every one is globally valid and independently replayable.
"""
import sys

sys.path[:0] = ['exp/v76', 'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60',
                'exp/v13']

from qnc import Budget
from quc import QUC
from smc import SMC


class QSC(QUC, SMC):
    def __init__(self, inst, h, mine=True, order='2dom', mine_budget=12,
                 node_budget=2, use_clause=True, **kw):
        QUC.__init__(self, inst, h, **kw)
        # SMC fields (not calling SMC.__init__: QUC already built the LP
        # and the QNC state)
        self.mine = mine
        self.order = order
        self.mine_budget = mine_budget
        self.node_budget = node_budget
        self.use_clause = use_clause
        self.mine_probes = 0
        self.mine_hits = 0
        self.mine_fail = 0
        self.force_events = []
        self.force_log = {}
        self.conflict = None
        self.mine_clauses = 0

    def decide(self, budget=100000, nodecap=5000, max_rounds=60, topk=100):
        self.budget = budget
        self.nodecap = nodecap
        try:
            v, why = self._root_phase(max_rounds, topk)
            if v is None and why == 'continue':
                v, why = self._search([(0, 1)] * self.lp.base.N, 0)
        except Budget:
            v, why = None, 'budget'
        return v, self._stats(why)

    def audit_qsc(self):
        return self.audit_quc() and self.audit_smc()
