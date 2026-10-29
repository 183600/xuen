"""v9.0 DBS-ALC: distributed breadth-first support search.

Inherits v8.0 BRC-ALC (downward QSP proof engine, fault-tolerant certificate
layer, randomized SGS fallback) and adds a *deterministic upward* phase:

  * root LP z  ->  support tree
  * BFS level  =  number of tasks fixed to a support start time
  * node LP    =  current LP with those tasks fixed
  * infeasible child -> prune (optionally with a verified Farkas certificate)
  * integral child   -> read schedule, replay with check_schedule
  * feasible fractional child -> expand next level

The frontier is bulk-synchronous, so it can be partitioned over workers.  A
worker failure only loses its claimed nodes; the coordinator re-queues them
or reports them in the UNKNOWN frontier.  The randomized SGS constructor of
v8.0 remains as a fallback after the BFS budget is exhausted.
"""
import sys

sys.path[:0] = ['exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from rdf import RDF, check_schedule
from qnc import Budget


def _integral_schedule(q, z):
    """Read a complete schedule from an integral LP solution."""
    inst = q.inst
    n, m, p = inst['n'], inst['m'], inst['p']
    starts = [None] * n
    machs = [None] * n
    for i in range(n):
        cols = []
        for cc, key in enumerate(q.lp.cols):
            if key[0] == i and z[cc] > 1 - 1e-7:
                cols.append((key[-1], key[1] if len(key) > 2 else None))
        if len(cols) != 1:
            return None
        t, k = cols[0]
        starts[i] = t
        if q.elig:
            if k is None:
                return None
            machs[i] = k
    if not q.elig:
        busy = [[] for _ in range(m)]
        for i in sorted(range(n), key=lambda i: (starts[i], i)):
            t = starts[i]
            for k in inst['elig'][i]:
                if all(t + p[i] <= a or t >= b for (a, b) in busy[k]):
                    machs[i] = k
                    busy[k].append((t, t + p[i]))
                    break
            if machs[i] is None:
                return None
    if check_schedule(inst, q.h, starts, machs):
        return starts, machs
    return None


class DBS(RDF):
    def __init__(self, inst, h, bfs_on=True, bfs_lp_cap=32, bfs_depth=6,
                 bfs_width=0, bfs_certify=False, **kw):
        super().__init__(inst, h, **kw)
        self.bfs_on = bfs_on
        self.bfs_lp_cap = bfs_lp_cap
        self.bfs_depth_cap = bfs_depth
        self.bfs_width = bfs_width          # 0 = full BFS, >0 = beam
        self.bfs_certify = bfs_certify
        self.bfs_lp = 0
        self.bfs_nodes = 0
        self.bfs_pruned = 0
        self.bfs_integral = 0
        self.bfs_frontier = 0
        self.bfs_depth = 0
        self.bfs_beam = 0
        self.bfs_path = None
        self.bfs_ok = False
        self.bfs_certs = 0
        self.bfs_cert_fail = 0

    # ------------------------------------------------------------ helpers
    def _bfs_solve(self, assign):
        N = self.lp.base.N
        bounds = [(0, 1)] * N
        for i, t in assign.items():
            for cc, key in enumerate(self.lp.cols):
                if key[0] == i and key[-1] != t:
                    bounds[cc] = (0, 0)
        self.lp_solves += 1
        self.bfs_lp += 1
        return self.lp.solve(bounds), bounds

    def _bfs_support(self, z):
        n = self.inst['n']
        out = {}
        for i in range(n):
            d = {}
            for cc, key in enumerate(self.lp.cols):
                if key[0] == i and z[cc] > 1e-7:
                    d[key[-1]] = d.get(key[-1], 0.0) + float(z[cc])
            out[i] = d
        return out

    def _bfs_score(self, z):
        sup = self._bfs_support(z)
        nf = sum(1 for d in sup.values() if len(d) >= 2)
        fm = sum(sum(min(v, 1 - v) for v in d.values())
                 for d in sup.values())
        return (nf, fm)

    def _bfs_certificate(self, assign):
        if not self.bfs_certify:
            return
        # Fixing s_i=t is equivalent to forbidding every column of task i
        # whose start is not t (the LP equality then forces the t-columns).
        F = set()
        for i, t in assign.items():
            for cc, key in enumerate(self.lp.cols):
                if key[0] == i and key[-1] != t:
                    F.add((i, key[-1]))
        cert, _ = self._farkas(self.lp, frozenset(F))
        if cert is None:
            self.bfs_cert_fail += 1
            return
        if self.verify_cert(cert, F):
            self.bfs_certs += 1
        else:
            self.bfs_cert_fail += 1

    def verify_cert(self, cert, F):
        from cert import verify
        return verify(self.inst, self.h, cert, forbid=F,
                      elig_aware=self.elig)

    # -------------------------------------------------------------- BFS
    def _bfs_support_search(self, z0):
        """Bulk-synchronous BFS over the dynamic support tree."""
        self.bfs_nodes += 1
        res = None
        # root solve is the phase-A LP; reuse z0 instead of re-solving.
        z = z0
        got = _integral_schedule(self, z)
        if got is not None:
            self.schedule, self.machine = got
            self.yes_ok = True
            self.bfs_ok = True
            self.bfs_integral += 1
            self.bfs_path = []
            return True
        frontier = [({}, z)]
        seen = set()
        depth = 0
        while frontier and depth < self.bfs_depth_cap \
                and self.bfs_lp < self.bfs_lp_cap:
            self.bfs_frontier = max(self.bfs_frontier, len(frontier))
            children = []
            for assign, zc in frontier:
                sup = self._bfs_support(zc)
                cand = [(len(d), i, d) for i, d in sup.items()
                        if i not in assign and len(d) >= 2]
                if not cand:
                    continue
                cand.sort(reverse=True)
                _, i, d = cand[0]
                for t in sorted(d):
                    a2 = dict(assign)
                    a2[i] = t
                    key = tuple(sorted(a2.items()))
                    if key in seen:
                        continue
                    seen.add(key)
                    if self.bfs_lp >= self.bfs_lp_cap:
                        break
                    res, bounds = self._bfs_solve(a2)
                    self.bfs_nodes += 1
                    if res.status != 0:
                        self.bfs_pruned += 1
                        self._bfs_certificate(a2)
                        continue
                    z2 = res.x
                    got = _integral_schedule(self, z2)
                    if got is not None:
                        self.schedule, self.machine = got
                        self.yes_ok = True
                        self.bfs_ok = True
                        self.bfs_integral += 1
                        self.bfs_depth = depth + 1
                        self.bfs_path = sorted(a2.items())
                        return True
                    children.append((self._bfs_score(z2), a2, z2))
            if not children:
                break
            if self.bfs_width > 0:
                children.sort(key=lambda x: (x[0][0], x[0][1]))
                children = children[:self.bfs_width]
                self.bfs_beam += 1
            frontier = [(a, zc) for _, a, zc in children]
            depth += 1
        self.bfs_depth = depth
        return False

    # ------------------------------------------------------------ decide
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
        if v is None and self.root_z is None:
            res = self.lp.solve([(0, 1)] * self.lp.base.N)
            self.lp_solves += 1
            if res.status == 2:
                v, why = False, 'root-core'
            elif res.status == 0:
                self.root_z = __import__('numpy').array(res.x, copy=True)

        # phase B0: deterministic support BFS (new in v9.0)
        if v is None and self.bfs_on and self.root_z is not None:
            if self._bfs_support_search(self.root_z):
                v, why = True, 'yes-bfs'

        # phase B1/B2: randomized SGS fallback (v8.0)
        if v is None and self.root_z is not None:
            if self._yes_construct(self.root_z, self.yes_trials1,
                                   self.yes_nodecap1):
                v, why = True, 'yes-lp-small'
        if v is None and self.root_z is not None \
                and self.yes_nodes < self.yes_node_budget:
            if self._yes_construct(self.root_z, self.yes_trials2,
                                   self.yes_nodecap2):
                v, why = True, 'yes-lp'

        # phase C: full NO search
        if v is None:
            self.budget = self.lp_solves + budget
            self.nodecap = self.nodes + nodecap
            try:
                v, why = self._search([(0, 1)] * self.lp.base.N, 0)
            except Budget:
                v, why = None, 'budget'
        return v, self._stats(why)

    def _stats(self, why):
        st = super()._stats(why)
        st.update(bfs_on=self.bfs_on, bfs_lp=self.bfs_lp,
                  bfs_nodes=self.bfs_nodes, bfs_pruned=self.bfs_pruned,
                  bfs_integral=self.bfs_integral,
                  bfs_frontier=self.bfs_frontier, bfs_depth=self.bfs_depth,
                  bfs_beam=self.bfs_beam, bfs_ok=self.bfs_ok,
                  bfs_certs=self.bfs_certs,
                  bfs_cert_fail=self.bfs_cert_fail,
                  bfs_path=self.bfs_path)
        return st
