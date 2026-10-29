"""Lazy-integral SD: add precedence (SD) cuts only at integral candidates.

At a fractional node the capacity-only start-time LP is solved; if the node
LP is infeasible, the Farkas certificate is still valid for the true integer
problem (it uses a subset of valid rows).  If the LP is integral we verify
all SD rows and add violated ones, re-solving until the integral point is
feasible or a cut makes the node infeasible.  This is a sound lazy
constraint algorithm and gives a controlled *weak-LP* regime: fractional
nodes see only capacity, so branching is much deeper than v6.1 ALC.
"""
import sys
sys.path[:0]=['exp/v71','exp/v61','exp/v60','exp/v13']
from qnc import QNC


class WeakQNC(QNC):
    def _solve(self, bounds, max_rounds, topk):
        res = None
        for rnd in range(max_rounds):
            if self.lp_solves >= self.budget:
                from qnc import Budget
                raise Budget
            res = self.lp.solve(bounds)
            self.lp_solves += 1
            if res.status != 0:
                return res, None
            z = res.x
            integral = not any(1e-7 < z[c] < 1 - 1e-7
                               for c in range(self.lp.N))
            if not integral:
                return res, z
            # integral candidate: enforce all SD rows
            viol = self.lp.separate(z, topk=topk)
            if not viol:
                return res, z
            added = 0
            for _, i, j, t in viol:
                if (i, j, t) not in self.lp.cutset:
                    self.lp.cutset.add((i, j, t))
                    self.lp.cuts.append((i, j, t))
                    added += 1
            if added == 0:
                return res, z
        return res, (res.x if res is not None and res.status == 0 else None)
