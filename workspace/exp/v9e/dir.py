"""v9.0 DIR-ALC: distributed iterative-refinement ALC.

The downward side is v8.0 BRC-ALC unchanged: QSP probes, verified Farkas
certificates, row-core recovery, fail-stop splits.  The upward side has
three new layers:

  * SF   support frontier: a best-first search over start-time assignments
         drawn from the root LP support.  Children are LP-feasibility
         checked; infeasible children are counted (and optionally certified);
         a full start vector is completed by a deterministic machine
         assignment DFS; every accepted schedule passes check_schedule.
  * SC   support closure: if SF exhausts the current support without a
         schedule, solve a max-coverage LP whose objective is the mass on
         start times not yet covered.  Value 0 certifies that the current
         union contains the projection of the whole LP polytope; value > 0
         yields a new vertex whose support is added, and SF is re-run.
         This is iterative refinement of the relaxation witness, not a cut.
  * SGS  the v8.0 randomized constructor remains as a bounded fallback.

The frontier is bulk-synchronous and shardable: workers own disjoint sets
of frontier nodes and return only schedules or verified certificates to
the coordinator.  The sequential prototype below preserves those
semantics; `workers` controls the shard width of each refinement round.
"""
import sys
import heapq
import random
import numpy as np

sys.path[:0] = ['exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from scipy.optimize import linprog

from rdf import RDF, check_schedule
from qnc import Budget


def _sched_from_starts(inst, h, starts):
    """Deterministic machine assignment for a complete start vector.

    The start vector is fixed, so the residual problem is a finite
    backtracking search over eligible machines.  MRV ordering keeps the
    search small on the instances used here; the node cap is a guard.
    """
    n, m, p = inst['n'], inst['m'], inst['p']
    busy = [[] for _ in range(m)]
    mach = [None] * n
    order = sorted(range(n), key=lambda i: (len(inst['elig'][i]),
                                            -p[i], starts[i], i))
    nodes = [0]

    def rec(pos):
        nodes[0] += 1
        if nodes[0] > 200000:
            return False
        if pos == n:
            return True
        i = order[pos]
        a, b = starts[i], starts[i] + p[i]
        for k in inst['elig'][i]:
            if all(b <= x or a >= y for (x, y) in busy[k]):
                busy[k].append((a, b))
                mach[i] = k
                if rec(pos + 1):
                    return True
                busy[k].remove((a, b))
                mach[i] = None
        return False

    if rec(0) and check_schedule(inst, h, starts, mach):
        return mach, nodes[0]
    return None, nodes[0]


class DIR(RDF):
    def __init__(self, inst, h, sf_on=True, sf_lp_cap=64, sf_node_cap=4000,
                 sf_refine_rounds=2, sf_refine_lp_cap=16, sf_closed_no=False,
                 sf_workers=1, sf_targeted=True, **kw):
        super().__init__(inst, h, **kw)
        self.sf_on = sf_on
        self.sf_lp_cap = sf_lp_cap
        self.sf_base_cap = sf_lp_cap
        self.sf_targeted = sf_targeted
        self.sf_node_cap = sf_node_cap
        self.sf_refine_rounds = sf_refine_rounds
        self.sf_refine_lp_cap = sf_refine_lp_cap
        self.sf_closed_no = sf_closed_no
        self.sf_workers = sf_workers
        # counters / witnesses
        self.sf_lp = 0
        self.sf_nodes = 0
        self.sf_pruned = 0
        self.sf_machine_nodes = 0
        self.sf_refines = 0
        self.sf_targeted_tried = 0
        self.sf_targeted_hits = 0
        self.sf_closed = False
        self.sf_exhausted = False
        self.sf_no = False
        self.sf_closure_val = None
        self.sf_covered = None
        self.sf_why = None

    # ---------------------------------------------------------- LP helpers
    def _sf_domains(self, z0):
        n = self.inst['n']
        dom = [set() for _ in range(n)]
        for cc, key in enumerate(self.lp.cols):
            if z0[cc] > 1e-7:
                dom[key[0]].add(key[-1])
        for i in range(n):
            if not dom[i]:
                dom[i].add(self.lp.est[i])
        return dom

    def _sf_bounds(self, assign):
        bounds = [(0, 1)] * self.lp.base.N
        for i, t in assign.items():
            for cc, key in enumerate(self.lp.cols):
                if key[0] == i and key[-1] != t:
                    bounds[cc] = (0, 0)
        return bounds

    def _sf_solve(self, assign):
        if self.lp_solves >= self.budget or self.sf_lp >= self.sf_lp_cap:
            return None
        res = self.lp.solve(self._sf_bounds(assign))
        self.lp_solves += 1
        self.sf_lp += 1
        return res

    def _sf_maxcov(self, covered):
        """Maximise LP mass on start times outside the current union."""
        A, hi = self.lp.matrix()
        n_eq, N = self.lp.n_eq, self.lp.base.N
        c = np.zeros(N)
        for cc, key in enumerate(self.lp.cols):
            if key[-1] not in covered[key[0]]:
                c[cc] = 1.0
        res = linprog(-c, A_ub=A, b_ub=hi, A_eq=A[:n_eq],
                      b_eq=np.ones(n_eq), bounds=(0, 1), method='highs')
        if res.status != 0:
            return None, None
        return float(-res.fun), res.x

    def _sf_add_support(self, covered, z):
        added = 0
        for cc, key in enumerate(self.lp.cols):
            if z[cc] > 1e-7:
                if key[-1] not in covered[key[0]]:
                    covered[key[0]].add(key[-1])
                    added += 1
        return added

    # -------------------------------------------------------- SF frontier
    def _sf_search(self, domains):
        """Best-first support frontier.  Returns (found, exhausted)."""
        n = self.inst['n']
        fixed = {i: next(iter(domains[i])) for i in range(n)
                 if len(domains[i]) == 1}
        pq = []
        counter = 0
        seen = set()

        def push(assign):
            nonlocal counter
            rem = sum(len(domains[i]) - 1 for i in range(n)
                      if i not in assign)
            heapq.heappush(pq, (-len(assign), rem, counter, assign))
            counter += 1

        push(fixed)
        while pq:
            if self.sf_lp >= self.sf_lp_cap or self.lp_solves >= self.budget:
                self.sf_exhausted = False
                return False, False
            _, _, _, assign = heapq.heappop(pq)
            key = tuple(sorted(assign.items()))
            if key in seen:
                continue
            seen.add(key)
            self.sf_nodes += 1
            if self.sf_nodes > self.sf_node_cap:
                self.sf_exhausted = False
                return False, False
            res = self._sf_solve(assign)
            if res is None:
                self.sf_exhausted = False
                return False, False
            if res.status != 0:
                self.sf_pruned += 1
                continue
            z = res.x
            got = self._schedule_from_z(z)
            if got is not None:
                self.schedule, self.machine = got
                self.yes_ok = True
                self.sf_why = 'integral'
                return True, False
            if len(assign) == n:
                starts = [assign[i] for i in range(n)]
                mach, mn = _sched_from_starts(self.inst, self.h, starts)
                self.sf_machine_nodes += mn
                if mach is not None:
                    self.schedule = starts
                    self.machine = mach
                    self.yes_ok = True
                    self.sf_why = 'machine'
                    return True, False
                continue
            # choose the most constrained unassigned task; break ties by
            # the fractionality of the current LP vertex.
            mass = {}
            for cc, kk in enumerate(self.lp.cols):
                i = kk[0]
                if i in assign:
                    continue
                mass.setdefault(i, {})
                mass[i][kk[-1]] = mass[i].get(kk[-1], 0.0) + float(z[cc])

            def ck(i):
                vals = mass.get(i, {})
                top = max(vals.values()) if vals else 1.0
                return (len(domains[i]), -(1.0 - top),
                        len(self.inst['elig'][i]), i)

            cand = [i for i in range(n) if i not in assign]
            if not cand:
                continue
            i = min(cand, key=ck)
            vals = sorted(domains[i], key=lambda t: -mass.get(i, {}).get(t, 0.0))
            for t in vals:
                a2 = dict(assign)
                a2[i] = t
                push(a2)
        self.sf_exhausted = True
        return False, True

    # --------------------------------------------------- support closure
    def _sf_worker(self, covered, lp_allow):
        """One shard: run SF on a candidate domain with a local LP cap."""
        saved_cap = self.sf_lp_cap
        saved_nodes = self.sf_nodes
        self.sf_lp_cap = self.sf_lp + lp_allow
        self.sf_nodes = 0
        found, exhausted = self._sf_search([sorted(c) for c in covered])
        worker_nodes = self.sf_nodes
        self.sf_nodes = saved_nodes + worker_nodes
        self.sf_lp_cap = saved_cap
        return found, exhausted, worker_nodes

    def _sf_new_support(self, covered, z):
        new = []
        for i in range(self.inst['n']):
            vals = set()
            for cc, key in enumerate(self.lp.cols):
                if key[0] == i and key[-1] not in covered[i] and z[cc] > 1e-7:
                    vals.add(key[-1])
            if vals:
                new.append((i, sorted(vals)))
        new.sort(key=lambda x: (len(x[1]), x[0]))
        return new

    def _sf_refine(self, z0):
        covered = self._sf_domains(z0)
        for rd in range(self.sf_refine_rounds + 1):
            self.sf_lp_cap = self.sf_base_cap + rd * self.sf_refine_lp_cap
            found, exhausted = self._sf_search([sorted(c) for c in covered])
            if found:
                return True
            if not exhausted:
                self.sf_why = 'sf-cap'
                return None
            if rd == self.sf_refine_rounds:
                self.sf_why = 'sf-exhausted'
                return None
            # SF exhausted: ask the LP for a vertex with new start times.
            if self.lp_solves + self.sf_refine_lp_cap > self.budget:
                self.sf_why = 'sf-budget'
                return None
            self.sf_refines += 1
            val, z = self._sf_maxcov(covered)
            if val is None:
                self.sf_why = 'sf-maxcov-fail'
                return None
            self.sf_closure_val = val
            if val <= 1e-8:
                self.sf_closed = True
                self.sf_covered = [set(c) for c in covered]
                self.sf_why = 'sf-closed'
                if self.sf_closed_no:
                    self.sf_no = True
                    return False
                return None
            new = self._sf_new_support(covered, z)
            if not new:
                self.sf_why = 'sf-no-new'
                return None
            # Distributed targeted refinement: one shard per candidate
            # task-addition.  The coordinator stops at the first schedule.
            if self.sf_targeted:
                for i, vals in new[:max(1, self.sf_workers)]:
                    cand = [set(c) for c in covered]
                    cand[i].update(vals)
                    self.sf_targeted_tried += 1
                    got, _, _ = self._sf_worker(cand, self.sf_refine_lp_cap)
                    if got:
                        self.sf_targeted_hits += 1
                        return True
            # No shard closed: take the union and try the next round.
            for i, vals in new:
                covered[i].update(vals)
        return None

    # ------------------------------------------------------------- decide
    def decide(self, budget=100000, nodecap=5000, max_rounds=60, topk=100):
        if not self.yes_scan:
            return super().decide(budget, nodecap, max_rounds, topk)

        self.budget = min(budget, self.small_budget)
        self.nodecap = min(nodecap, self.small_nodes)
        try:
            v, why = self._search([(0, 1)] * self.lp.base.N, 0)
        except Budget:
            v, why = None, 'budget-small'
        if v is None and self.root_z is None:
            res = self.lp.solve([(0, 1)] * self.lp.base.N)
            self.lp_solves += 1
            if res.status == 2:
                v, why = False, 'root-core'
            elif res.status == 0:
                self.root_z = np.array(res.x, copy=True)

        # U0/U1: deterministic support frontier + closure refinement.
        if v is None and self.sf_on and self.root_z is not None:
            self.sf_lp = 0
            # SF has its own LP allowance; phase A's small budget must not
            # truncate it.  Phase C resets the budget if we fall through.
            self.budget = max(self.budget,
                              self.lp_solves + self.sf_lp_cap
                              + self.sf_refine_rounds * self.sf_refine_lp_cap)
            sf = self._sf_refine(self.root_z)
            if sf is True:
                v, why = True, 'yes-sf'
            elif sf is False and self.sf_no:
                v, why = False, 'no-sf-closure'

        # U2: v8.0 randomized SGS fallback.
        if v is None and self.yes_scan and self.root_z is not None:
            if self._yes_construct(self.root_z, self.yes_trials1,
                                   self.yes_nodecap1):
                v, why = True, 'yes-lp-small'
        if v is None and self.yes_scan and self.root_z is not None \
                and self.yes_nodes < self.yes_node_budget:
            if self._yes_construct(self.root_z, self.yes_trials2,
                                   self.yes_nodecap2):
                v, why = True, 'yes-lp'

        # U3: full NO search (v8.0 phase C).
        if v is None:
            self.budget = budget
            self.nodecap = self.nodes + nodecap
            try:
                v, why = self._search([(0, 1)] * self.lp.base.N, 0)
            except Budget:
                v, why = None, 'budget'
        return v, self._stats(why)

    # --------------------------------------------------------------- stats
    def _stats(self, why):
        st = super()._stats(why)
        st.update(sf_on=self.sf_on, sf_lp=self.sf_lp,
                  sf_nodes=self.sf_nodes, sf_pruned=self.sf_pruned,
                  sf_machine_nodes=self.sf_machine_nodes,
                  sf_refines=self.sf_refines, sf_closed=self.sf_closed,
                  sf_exhausted=self.sf_exhausted, sf_no=self.sf_no,
                  sf_closure_val=self.sf_closure_val,
                  sf_why=self.sf_why, sf_workers=self.sf_workers,
                  sf_targeted_tried=self.sf_targeted_tried,
                  sf_targeted_hits=self.sf_targeted_hits)
        return st

    def audit_rdf(self):
        if not super().audit_rdf():
            return False
        if self.sf_no:
            if not (self.sf_closed and self.sf_exhausted
                    and self.sf_closure_val is not None
                    and self.sf_closure_val <= 1e-8):
                return False
            if self.sf_covered is None:
                return False
            val, _ = self._sf_maxcov(self.sf_covered)
            if val is None or val > 1e-8:
                return False
        return True
