"""v9.0 CHD-ALC: convex-hull discrepancy search for the upward reduction.

Inherits v8.0 BRC-ALC unchanged on the downward side (QSP probes, verified
Farkas certificates, row-core recovery, fail-stop splits).  Replaces the
randomized SGS constructor on the upward side by a deterministic,
bounded-discrepancy search:

  * cheap order:  precedence heads/tails + root-LP mean/argmax
  * hull order:   projection of the LP polytope onto each start coordinate
                  (n LP minimizations, built from one shared matrix)
  * LDS:          iterative deepening on the number of deviations from the
                  order; first task / first machine are discrepancy 0
  * replay:       every candidate passes check_schedule before it is accepted

The hull is used as an *ordering oracle*, not as a constraint.  A wrong or
numerically noisy projection can only change the search order, never the
set of schedules that LDS can reach at a sufficiently large discrepancy.
"""
import sys
import math
import time

sys.path[:0] = ['exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

import numpy as np
from scipy.optimize import linprog

from rdf import RDF, check_schedule, _heads_latest, _insert, _earliest
from qnc import Budget


def _lp_distribution(q, z):
    """Per-task start-time distribution of one root LP solution."""
    n = q.inst['n']
    out = {}
    for i in range(n):
        d = {}
        mass = 0.0
        for cc, key in enumerate(q.lp.cols):
            if key[0] == i:
                v = float(z[cc])
                if v > 1e-9:
                    d[key[-1]] = d.get(key[-1], 0.0) + v
                    mass += v
        if mass <= 1e-12:
            out[i] = {q.lp.est[i]: 1.0}
        else:
            out[i] = {t: v / mass for t, v in d.items()}
    return out


def _mean_rank(dist, est):
    return {i: sum(t * v for t, v in d.items()) for i, d in dist.items()}


def _argmax_rank(dist, est):
    return {i: (max(d, key=d.get) if d else est[i])
            for i, d in dist.items()}


class CHD(RDF):
    def __init__(self, inst, h, cheap_disc=2, cheap_nodes=16000,
                 cheap_nodecap=4000, hull_disc=4, hull_nodes=60000,
                 hull_on=True, random_fallback=True, **kw):
        super().__init__(inst, h, **kw)
        self.cheap_disc = cheap_disc
        self.cheap_nodes = cheap_nodes
        self.cheap_nodecap = cheap_nodecap
        self.hull_disc = hull_disc
        self.hull_nodes = hull_nodes
        self.hull_on = hull_on
        self.random_fallback = random_fallback
        # counters
        self.phase = None
        self.lds_calls = 0
        self.lds_nodes = 0
        self.lds_rank = None
        self.lds_disc = None
        self.hull_calls = 0
        self.hull_lp = 0
        self.hull_fail = 0
        self.hull_time = 0.0
        self.lo = None
        self.used_random = False

    # ------------------------------------------------------------- replay
    def _accept(self, got, phase, rank=None, disc=None):
        if got is None:
            return False
        starts, machs = got
        if not check_schedule(self.inst, self.h, starts, machs):
            return False
        self.schedule = list(starts)
        self.machine = list(machs)
        self.yes_ok = True
        self.phase = phase
        self.lds_rank = rank
        self.lds_disc = disc
        return True

    # ---------------------------------------------------------------- LDS
    def _lds(self, rank, nodecap, max_disc, lower=None, upper=None):
        """Iterative-deepening discrepancy search on active schedules.

        Returns (starts, machines, nodes_used, discrepancy) or
        (None, nodes_used, last_disc, None).  The first available task and
        the first machine (earliest start) are discrepancy 0; every other
        task or machine choice costs one unit of discrepancy.
        """
        inst, h = self.inst, self.h
        n, m, p = inst['n'], inst['m'], inst['p']
        est, qt, latest = _heads_latest(inst, h)
        if lower is not None:
            est = [max(est[i], lower[i]) for i in range(n)]
        if upper is not None:
            latest = [min(latest[i], upper[i]) for i in range(n)]

        def one_run(dmax):
            starts = [None] * n
            machs = [None] * n
            busy = [[] for _ in range(m)]
            rem = [len(inst['pred'][i]) for i in range(n)]
            predfin = [0] * n
            done = [False] * n
            nodes = [0]

            def rec(d):
                nodes[0] += 1
                if nodes[0] > nodecap:
                    return None
                if all(done):
                    return True
                av = [i for i in range(n) if not done[i] and rem[i] == 0]
                if not av:
                    return False
                av.sort(key=lambda i: (rank[i], i))
                for oi, i in enumerate(av):
                    cost = 0 if oi == 0 else 1
                    if cost > d:
                        continue
                    base = max(est[i], predfin[i])
                    opts = []
                    for k in inst['elig'][i]:
                        tt = _earliest(busy[k], base, p[i])
                        if tt <= latest[i]:
                            opts.append((tt, k))
                    opts.sort()
                    for mi, (tt, k) in enumerate(opts):
                        c2 = cost + (0 if mi == 0 else 1)
                        if c2 > d:
                            continue
                        starts[i] = tt
                        machs[i] = k
                        done[i] = True
                        _insert(busy, k, tt, tt + p[i])
                        old = [(j, predfin[j]) for j in inst['succ'][i]]
                        for j in inst['succ'][i]:
                            predfin[j] = max(predfin[j], tt + p[i])
                            rem[j] -= 1
                        r = rec(d - c2)
                        if r is True:
                            return True
                        if r is None:
                            return None
                        for j, v in old:
                            predfin[j] = v
                            rem[j] += 1
                        busy[k].remove((tt, tt + p[i]))
                        done[i] = False
                        starts[i] = None
                        machs[i] = None
                return False

            r = rec(dmax)
            return r, nodes[0], starts, machs

        used = 0
        last = 0
        for d in range(max_disc + 1):
            last = d
            r, nd, starts, machs = one_run(d)
            used += nd
            if r is True and check_schedule(inst, h, starts, machs):
                return (starts, machs), used, d
            if r is None:
                return None, used, d
            if used > nodecap:
                return None, used, d
        return None, used, last

    # --------------------------------------------------------- cheap phase
    def _cheap_lds(self):
        n = self.inst['n']
        est, qt, latest = _heads_latest(self.inst, self.h)
        dist = _lp_distribution(self, self.root_z)
        ranks = [
            ('mean', _mean_rank(dist, est)),
            ('latest', {i: latest[i] for i in range(n)}),
            ('argmax', _argmax_rank(dist, est)),
            ('est', {i: est[i] for i in range(n)}),
        ]
        used = 0
        for name, rk in ranks:
            rk = {i: rk[i] + i * 1e-9 for i in range(n)}
            cap = min(self.cheap_nodecap, self.cheap_nodes - used)
            got, nd, d = self._lds(rk, cap, self.cheap_disc,
                                   lower={i: est[i] for i in range(n)},
                                   upper={i: latest[i] for i in range(n)})
            used += nd
            self.lds_nodes += nd
            self.lds_calls += 1
            if got is not None:
                if self._accept(got, 'cheap:' + name, name, d):
                    return True
            if used >= self.cheap_nodes:
                break
        return False

    # ---------------------------------------------------------- hull phase
    def _project_lo(self, bounds):
        """Min over the LP polytope of each task's start time.

        One matrix is shared by all n objectives.  The values are used only
        as ordering keys; they are not asserted as constraints.
        """
        n = self.inst['n']
        A, hi = self.lp.matrix()
        out = {}
        for i in range(n):
            if self.lp_solves >= self.budget:
                raise Budget
            c = np.zeros(self.lp.base.N)
            for cc, key in enumerate(self.lp.cols):
                if key[0] == i:
                    c[cc] = key[-1]
            res = linprog(c, A_ub=A, b_ub=hi,
                          A_eq=A[:self.lp.n_eq], b_eq=np.ones(self.lp.n),
                          bounds=bounds, method='highs')
            self.lp_solves += 1
            self.hull_lp += 1
            if res.status == 0:
                out[i] = float(res.fun)
            else:
                self.hull_fail += 1
                out[i] = self.lp.est[i]
        return out

    def _hull_lds(self):
        n = self.inst['n']
        base, _ = self._apply_force([(0, 1)] * self.lp.base.N)
        t0 = time.time()
        try:
            lo = self._project_lo(base)
        except Budget:
            self.hull_time += time.time() - t0
            return False
        self.hull_time += time.time() - t0
        self.hull_calls += 1
        self.lo = lo
        est, qt, latest = _heads_latest(self.inst, self.h)
        dist = _lp_distribution(self, self.root_z)
        ranks = [
            ('lo', {i: lo[i] + i * 1e-9 for i in range(n)}),
            ('latest', {i: latest[i] + i * 1e-9 for i in range(n)}),
            ('mean', {i: _mean_rank(dist, est)[i] + i * 1e-9
                      for i in range(n)}),
        ]
        used = 0
        for name, rk in ranks:
            got, nd, d = self._lds(rk, self.hull_nodes - used,
                                   self.hull_disc,
                                   lower={i: est[i] for i in range(n)},
                                   upper={i: latest[i] for i in range(n)})
            used += nd
            self.lds_nodes += nd
            self.lds_calls += 1
            if got is not None:
                if self._accept(got, 'hull:' + name, name, d):
                    return True
            if used >= self.hull_nodes:
                break
        return False

    # ------------------------------------------------------------- decide
    def decide(self, budget=100000, nodecap=5000, max_rounds=60, topk=100):
        if not self.yes_scan:
            return super().decide(budget, nodecap, max_rounds, topk)

        # phase A: small-budget NO search
        self.budget = min(budget, self.small_budget)
        self.nodecap = min(nodecap, self.small_nodes)
        try:
            v, why = self._search([(0, 1)] * self.lp.base.N, 0)
        except Budget:
            v, why = None, 'budget-small'
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
                self.root_z = np.array(res.x, copy=True)

        # phase B0: cheap deterministic LDS
        if self.root_z is not None and self.cheap_disc >= 0:
            if self._cheap_lds():
                return True, self._stats('yes-cheap')

        # phase B1: projection-hull LDS
        if self.root_z is not None and self.hull_on:
            self.budget = max(self.lp_solves + self.inst['n'], budget)
            if self._hull_lds():
                return True, self._stats('yes-hull')

        # phase B2: v8 randomized fallback (off on the deterministic path)
        if self.root_z is not None and self.random_fallback:
            if self._yes_construct(self.root_z, self.yes_trials1,
                                   self.yes_nodecap1):
                self.used_random = True
                self.phase = 'B2'
                return True, self._stats('yes-random-small')
            if self.yes_nodes < self.yes_node_budget:
                if self._yes_construct(self.root_z, self.yes_trials2,
                                       self.yes_nodecap2):
                    self.used_random = True
                    self.phase = 'B2'
                    return True, self._stats('yes-random')

        # phase C: full NO search
        self.budget = budget
        self.nodecap = self.nodes + nodecap
        try:
            v, why = self._search([(0, 1)] * self.lp.base.N, 0)
        except Budget:
            v, why = None, 'budget'
        self.phase = 'C'
        return v, self._stats(why)

    # -------------------------------------------------------------- stats
    def _stats(self, why):
        st = super()._stats(why)
        st.update(phase=self.phase, lds_calls=self.lds_calls,
                  lds_nodes=self.lds_nodes, lds_rank=self.lds_rank,
                  lds_disc=self.lds_disc, hull_calls=self.hull_calls,
                  hull_lp=self.hull_lp, hull_fail=self.hull_fail,
                  hull_time=round(self.hull_time, 4),
                  used_random=self.used_random)
        return st

    def audit_chd(self):
        if not self.audit_rdf():
            return False
        if self.schedule is not None:
            if not check_schedule(self.inst, self.h, self.schedule,
                                  self.machine):
                return False
        return True
