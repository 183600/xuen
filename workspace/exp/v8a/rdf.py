"""v8.0 BRC-ALC: bidirectional reduction with certified witnesses.

This module builds on v7.6 QSP (support probes, force recursion) and v7.2
QUC (unit probes, support lemma).  It adds the *upward* reduction and the
fault-tolerant witness layer:

  * downward:  LP(C) -> delete columns/support -> Farkas force -> reduced LP
  * upward:    LP(C) distribution -> sample priority list -> serial SGS DFS
  * recovery:  failed Farkas extraction -> dual row-core re-extraction
  * fail-stop: missing leaf certificate -> certified domain split

Every verdict is backed by a replayable object: a Farkas leaf or force for
NO, an independently replayed schedule for YES.  The constructor never
returns a schedule that has not passed the checker.
"""
import sys
import random
import numpy as np
import scipy.sparse as sp
from scipy.optimize import linprog

sys.path[:0] = ['exp/v76', 'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60',
                'exp/v13']

from qnc import Budget, farkas_int
from quc import QUC, _del_bounds
from qsp import QSP
from smc import farkas_obj, _support
from cert import DENS, verify, _row_meta
import po


# ------------------------------------------------------------------ helpers
def _raw_dual(lp, forbid):
    """Solve the b^T y = -1 dual; return raw rows and the dual vector."""
    A, hi = lp.matrix()
    n_eq, N, n = lp.n_eq, lp.base.N, lp.n
    r = A.shape[0] - n_eq
    present = np.array([cc for cc, key in enumerate(lp.cols)
                        if (key[0], key[-1]) not in forbid], dtype=np.int64)
    if len(present) == 0:
        return None
    B = sp.hstack([A[:n_eq].T, A[n_eq:].T]).tocsr()[present]
    b = np.concatenate([np.ones(n_eq), hi[n_eq:]])
    res = linprog(np.zeros(n_eq + r), A_ub=-B,
                  b_ub=np.zeros(len(present)), A_eq=[b], b_eq=[-1.0],
                  bounds=[(None, None)] * n_eq + [(0, None)] * r,
                  method='highs')
    if res.status != 0:
        return None
    return res.x, A, hi, b, present, n_eq


def _cert_from_y(lp, y, A, hi, b, present, dens=DENS):
    for D in dens:
        yi = np.rint(y * D).astype(np.int64)
        s = np.asarray(A.T.dot(yi)).ravel()
        bt = int(b.dot(yi))
        if s[present].min() >= 0 and bt < 0:
            meta = _row_meta(lp.base) + [('dom', i, j, t)
                                         for (i, j, t) in lp.cuts]
            yb = yi[lp.n_eq:]
            cert = dict(kind='packing', scale=D,
                        beta=[(m[1], m[2], int(yb[k]))
                              for k, m in enumerate(meta)
                              if m[0] == 'cap' and yb[k]],
                        dom=[(m[1], m[2], m[3], int(yb[k]))
                             for k, m in enumerate(meta)
                             if m[0] == 'dom' and yb[k]],
                        exp=[(m[1], m[2], int(yb[k]))
                             for k, m in enumerate(meta)
                             if m[0] == 'exp' and yb[k]],
                        alpha=[int(v) for v in yi[:lp.n]],
                        obj=bt, farkas=None,
                        cuts=[meta[k] for k in range(len(meta)) if yb[k]])
            return cert, s
    return None, None


def farkas_core(lp, forbid, dens=DENS):
    """Integer Farkas certificate on the dual row core.

    The full dual is solved first; rows with zero dual value are dropped,
    and the dual is re-solved on the remaining rows.  A certificate of the
    row-core LP is also a certificate of the full LP (the dropped rows get
    multiplier zero), so this is a reduction, not a relaxation.
    """
    raw = _raw_dual(lp, forbid)
    if raw is None:
        return None, None
    y, A, hi, b, present, n_eq = raw
    rows = [r for r in range(A.shape[0]) if abs(float(y[r])) > 1e-7]
    if not rows:
        return None, None
    if len(rows) == A.shape[0]:
        return _cert_from_y(lp, y, A, hi, b, present, dens)
    A2 = A[rows]
    b2 = b[rows]
    B2 = A2.T.tocsr()[present]
    bounds = [(None, None) if r < n_eq else (0, None) for r in rows]
    res2 = linprog(np.zeros(len(rows)), A_ub=-B2,
                   b_ub=np.zeros(len(present)), A_eq=[b2], b_eq=[-1.0],
                   bounds=bounds, method='highs')
    if res2.status != 0:
        return None, None
    y2 = np.zeros(A.shape[0])
    y2[rows] = res2.x
    return _cert_from_y(lp, y2, A, hi, b, present, dens)


def check_schedule(inst, h, start, mach):
    """Independent replay of a complete schedule."""
    n, m, p = inst['n'], inst['m'], inst['p']
    if start is None or mach is None or len(start) != n or len(mach) != n:
        return False
    for i in range(n):
        if start[i] is None or mach[i] is None:
            return False
        if start[i] < 0 or start[i] + p[i] > h:
            return False
        if mach[i] not in inst['elig'][i]:
            return False
    for i in range(n):
        for j in inst['succ'][i]:
            if start[j] < start[i] + p[i]:
                return False
    for k in range(m):
        js = sorted([i for i in range(n) if mach[i] == k],
                    key=lambda i: start[i])
        for a, b in zip(js, js[1:]):
            if start[a] + p[a] > start[b]:
                return False
    return True


def _heads_latest(inst, h):
    est, q = po.heads_tails(inst, 0, [0] * inst['n'])
    latest = [h - q[i] - inst['p'][i] for i in range(inst['n'])]
    return est, q, latest


def _insert(busy, k, a, b):
    busy[k].append((a, b))
    busy[k].sort()


def _earliest(busy_k, base, p):
    t = base
    for a, b in sorted(busy_k):
        if t + p <= a:
            break
        if t < b:
            t = b
    return t


# ------------------------------------------------------------------- engine
class RDF(QSP):
    def __init__(self, inst, h, yes_scan=True, yes_trials1=8,
                 yes_nodecap1=500, yes_trials2=48, yes_nodecap2=4000,
                 small_budget=12, small_nodes=200, ft_on=True, recover=True,
                 fail_calls=0, corrupt_calls=0, ft_budget=64,
                 yes_node_budget=60000, **kw):
        super().__init__(inst, h, **kw)
        self.yes_scan = yes_scan
        self.yes_trials1 = yes_trials1
        self.yes_nodecap1 = yes_nodecap1
        self.yes_trials2 = yes_trials2
        self.yes_nodecap2 = yes_nodecap2
        self.small_budget = small_budget
        self.small_nodes = small_nodes
        self.ft_on = ft_on
        self.recover_on = recover
        self.fail_left = fail_calls
        self.corrupt_left = corrupt_calls
        self.ft_budget = ft_budget
        self.yes_node_budget = yes_node_budget
        # counters
        self.root_z = None
        self.schedule = None
        self.machine = None
        self.yes_calls = 0
        self.yes_trials_used = 0
        self.yes_nodes = 0
        self.yes_ok = False
        self.recovered = 0
        self.forced_fail = 0
        self.corrupt_caught = 0
        self.corrupt_missed = 0
        self.leaf_missing = 0
        self.ft_splits = 0
        self.ft_stuck = 0

    # ------------------------------------------------------- extraction
    def _recover(self, lp, forbid):
        if not self.recover_on:
            return None, None
        cert, slack = farkas_core(lp, forbid)
        if cert is not None:
            self.recovered += 1
        return cert, slack

    def _corrupt(self, cert):
        bad = dict(cert)
        bad['alpha'] = list(cert['alpha'])
        if bad['alpha']:
            bad['alpha'][0] = bad['alpha'][0] + 1000003
        else:
            bad['beta'] = list(cert['beta']) + [(None, 0, 1000003)]
        return bad

    def _farkas(self, lp, forbid):
        """Farkas first (v7.x path), row-core recovery as a fallback."""
        if self.fail_left > 0:
            self.fail_left -= 1
            self.forced_fail += 1
            return self._recover(lp, forbid)
        cert, slack = farkas_int(lp, forbid)
        if cert is None:
            return self._recover(lp, forbid)
        if self.corrupt_left > 0:
            self.corrupt_left -= 1
            bad = self._corrupt(cert)
            if not verify(self.inst, self.h, bad, forbid=forbid,
                          elig_aware=self.elig):
                self.corrupt_caught += 1
                return self._recover(lp, forbid)
            self.corrupt_missed += 1
            return bad, slack
        return cert, slack

    def _extract(self, lp, forbid):
        return self._farkas(lp, forbid)

    # ---------------------------------------------------------- probes
    def _probe_unit(self, i, t):
        if self.lp_solves >= self.budget:
            raise Budget
        b = _del_bounds(self.lp, i, t)
        res = self.lp.solve(b)
        self.lp_solves += 1
        self.unit_probes += 1
        if res.status != 2:
            return False, None
        cert, _ = self._extract(self.lp, frozenset({(i, t)}))
        if cert is None:
            self.unit_fail += 1
            return False, None
        if not verify(self.inst, self.h, cert, forbid={(i, t)},
                      elig_aware=self.elig):
            self.unit_fail += 1
            return False, None
        self.unit_forced += 1
        return True, cert

    def _probe_support(self, i, S_i, bounds):
        if self.mine_probes >= self.mine_budget:
            raise Budget
        b2 = list(bounds)
        for cc, key in enumerate(self.lp.cols):
            if key[0] == i and key[-1] in S_i and b2[cc] != (0, 0):
                b2[cc] = (0, 0)
        res = self.lp.solve(b2)
        self.lp_solves += 1
        self.mine_probes += 1
        if res.status != 2:
            return None
        F = self._forbids(b2)
        cert, slack = self._extract(self.lp, F)
        if cert is None:
            self.mine_fail += 1
            return None
        E = frozenset((key[0], key[-1])
                      for cc, key in enumerate(self.lp.cols)
                      if (key[0], key[-1]) in F and slack[cc] < 0)
        if not E:
            self.mine_fail += 1
            return None
        if not verify(self.inst, self.h, cert, forbid=E,
                      elig_aware=self.elig):
            self.mine_fail += 1
            return None
        return E, cert

    # ------------------------------------------------------- leaf analyse
    def _analyse(self, F):
        self.cert_calls += 1
        cert, slack = self._farkas(self.lp, F)
        if cert is None:
            self.cert_fail += 1
            return None
        E = frozenset(key for cc, key in enumerate(self.lp.cols)
                      if key in F and slack[cc] < 0)
        if not E:
            E = frozenset(F)
        if E != frozenset(F) and not verify(self.inst, self.h, cert,
                                            forbid=E,
                                            elig_aware=self.elig):
            E = frozenset(F)
        if not verify(self.inst, self.h, cert, forbid=E,
                      elig_aware=self.elig):
            self.cert_fail += 1
            return None
        return cert, E

    def _schedule_from_z(self, z):
        """Read a complete schedule from an integral LP vertex."""
        inst = self.inst
        n, m, p = inst['n'], inst['m'], inst['p']
        starts = [None] * n
        machs = [None] * n
        for i in range(n):
            cols = []
            for cc, key in enumerate(self.lp.cols):
                if key[0] == i and z[cc] > 1 - 1e-7:
                    cols.append((key[-1], key[1] if len(key) > 2 else None))
            if len(cols) != 1:
                return None
            t, k = cols[0]
            starts[i] = t
            if self.elig:
                if k is None:
                    return None
                machs[i] = k
        if not self.elig:
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
        if check_schedule(inst, self.h, starts, machs):
            return starts, machs
        return None

    # ----------------------------------------------------- YES reduction
    def _lp_distribution(self, z):
        n = self.inst['n']
        dist = {}
        for i in range(n):
            d = {}
            mass = 0.0
            for cc, key in enumerate(self.lp.cols):
                if key[0] == i:
                    v = float(z[cc])
                    if v > 1e-9:
                        d[key[-1]] = d.get(key[-1], 0.0) + v
                        mass += v
            if mass <= 1e-12:
                d = {self.lp.est[i]: 1.0}
                mass = 1.0
            dist[i] = [(t, v / mass) for t, v in sorted(d.items())]
        return dist

    def _sample_rank(self, dist, rng):
        rank = {}
        for i, d in dist.items():
            u = rng.random()
            acc = 0.0
            t = d[-1][0]
            for tt, v in d:
                acc += v
                if u <= acc:
                    t = tt
                    break
            rank[i] = t + rng.random() * 1e-6
        return rank

    def _sgs_dfs(self, rank, nodecap, seed=0):
        rng = random.Random(seed)
        inst, h = self.inst, self.h
        n, m, p = inst['n'], inst['m'], inst['p']
        est, q, latest = _heads_latest(inst, h)
        starts = [None] * n
        machs = [None] * n
        busy = [[] for _ in range(m)]
        rem = [len(inst['pred'][i]) for i in range(n)]
        predfin = [0] * n
        done = [False] * n
        nodes = [0]

        def rec():
            nodes[0] += 1
            if nodes[0] > nodecap:
                return False
            if all(done):
                return True
            av = [i for i in range(n) if not done[i] and rem[i] == 0]
            if not av:
                return False
            av.sort(key=lambda i: (rank[i], i))
            for i in av:
                base = max(est[i], predfin[i])
                opts = []
                for k in inst['elig'][i]:
                    tt = _earliest(busy[k], base, p[i])
                    if tt <= latest[i]:
                        opts.append((tt, k))
                opts.sort()
                for tt, k in opts:
                    starts[i] = tt
                    machs[i] = k
                    done[i] = True
                    _insert(busy, k, tt, tt + p[i])
                    old = [(j, predfin[j]) for j in inst['succ'][i]]
                    for j in inst['succ'][i]:
                        predfin[j] = max(predfin[j], tt + p[i])
                        rem[j] -= 1
                    if rec():
                        return True
                    for j, v in old:
                        predfin[j] = v
                        rem[j] += 1
                    busy[k].remove((tt, tt + p[i]))
                    done[i] = False
                    starts[i] = None
                    machs[i] = None
                    if nodes[0] > nodecap:
                        return False
            return False

        ok = rec()
        self.yes_nodes += nodes[0]
        if ok and check_schedule(inst, h, starts, machs):
            return starts, machs
        return None

    def _yes_construct(self, z, trials, nodecap):
        self.yes_calls += 1
        dist = self._lp_distribution(z)
        rng = random.Random(20261023 + self.yes_calls * 7919)
        for r in range(trials):
            rem = self.yes_node_budget - self.yes_nodes
            if rem <= 0:
                return False
            self.yes_trials_used += 1
            rank = self._sample_rank(dist, rng)
            got = self._sgs_dfs(rank, min(nodecap, rem), seed=r)
            if got is not None:
                self.schedule, self.machine = got
                self.yes_ok = True
                return True
        return False

    # -------------------------------------------------------- FT splitting
    def _ft_split(self, bounds, depth):
        if self.ft_splits >= self.ft_budget:
            self.ft_stuck += 1
            return None, 'ft-budget'
        self.ft_splits += 1
        n = self.inst['n']
        best, best_n, best_times = None, 0, None
        for i in range(n):
            live = sorted(self._live(i, bounds))
            if len(live) > best_n:
                best, best_n, best_times = i, len(live), live
        if best is None or best_n <= 1:
            self.ft_stuck += 1
            return None, 'ft-stuck'
        mid = best_times[len(best_times) // 2]
        lo = list(bounds)
        hi2 = list(bounds)
        for cc, key in enumerate(self.lp.cols):
            if key[0] != best:
                continue
            if key[-1] > mid:
                lo[cc] = (0, 0)
            else:
                hi2[cc] = (0, 0)
        a, why = self._search(lo, depth + 1)
        if a is not False:
            return a, why
        return self._search(hi2, depth + 1)

    # -------------------------------------------------------------- search
    def _search(self, base, depth):
        self._cur_depth = depth
        loop = 0
        while True:
            bounds, _ = self._apply_force(base)
            i0 = self._empty_job(bounds) if self.use_empty else None
            if i0 is not None:
                self.empty_prunes += 1
                return False, 'empty'
            F = self._forbids(bounds)
            for E in self.clauses:
                if E <= F:
                    self.prunes += 1
                    return False, 'clause'
            if loop == 0:
                self.nodes += 1
                if self.nodes > self.nodecap:
                    raise Budget
            res, z = self._solve(bounds, 60, 100)
            if res.status == 2:
                got = self._learn(F)
                cert = got[0] if got is not None else None
                if cert is None:
                    self.leaf_missing += 1
                    if self.ft_on:
                        return self._ft_split(bounds, depth)
                return False, 'no'
            if z is None:
                return None, 'roundcap'
            frac = [(abs(z[cc] - 0.5), cc, key[0], key[-1])
                    for cc, key in enumerate(self.lp.cols)
                    if 1e-7 < z[cc] < 1 - 1e-7]
            if depth == 0 and self.root_z is None:
                self.root_z = np.array(z, copy=True)
            if not frac:
                got = self._schedule_from_z(z)
                if got is None:
                    return None, 'integral-unscheduled'
                self.schedule, self.machine = got
                self.yes_ok = True
                return True, 'yes'
            if depth == 0:
                self.root_frac = True
            if self.probe_on and self.probes_total < self.probe_budget \
                    and (not self.root_only or depth == 0):
                kind = self._portfolio(bounds, z)
                if kind in ('trap', 'cross', 'conflict'):
                    return False, 'probe-' + kind
                if kind == 'force':
                    self.re_solves += 1
                    loop += 1
                    continue
            frac.sort()
            _, cc, i, t = frac[0]
            times = sorted(self.domain(i))
            s = 0.0
            mid = t
            for tt in times:
                if self.elig:
                    s += sum(z[self.lp.idx[(i, k, tt)]]
                             for k in self.lp.base.elig[i]
                             if (i, k, tt) in self.lp.idx)
                else:
                    s += z[self.lp.idx[(i, tt)]]
                if s >= 0.5:
                    mid = tt
                    break
            if mid >= times[-1]:
                mid = times[-1] - 1
            lo = list(bounds)
            hi2 = list(bounds)
            for tt in times:
                if self.elig:
                    for k in self.lp.base.elig[i]:
                        if (i, k, tt) not in self.lp.idx:
                            continue
                        c2 = self.lp.idx[(i, k, tt)]
                        if tt > mid:
                            lo[c2] = (0, 0)
                        else:
                            hi2[c2] = (0, 0)
                else:
                    c2 = self.lp.idx[(i, tt)]
                    if tt > mid:
                        lo[c2] = (0, 0)
                    else:
                        hi2[c2] = (0, 0)
            a, why = self._search(lo, depth + 1)
            if a is not False:
                return a, why
            return self._search(hi2, depth + 1)

    # ------------------------------------------------------------ decide
    def decide(self, budget=100000, nodecap=5000, max_rounds=60, topk=100):
        if not self.yes_scan:
            # Pure NO mode: one QSP-equivalent search, no restart.
            self.budget = budget
            self.nodecap = nodecap
            try:
                v, why = self._search([(0, 1)] * self.lp.base.N, 0)
            except Budget:
                v, why = None, 'budget'
            return v, self._stats(why)
        self.budget = min(budget, self.small_budget)
        self.nodecap = min(nodecap, self.small_nodes)
        try:
            v, why = self._search([(0, 1)] * self.lp.base.N, 0)
        except Budget:
            v, why = None, 'budget-small'
        if v is None and self.yes_scan and self.root_z is None:
            # The root lazy separation can exhaust a small probe budget
            # before returning z.  One direct solve of the current (valid)
            # cut set supplies the constructor witness.
            res = self.lp.solve([(0, 1)] * self.lp.base.N)
            self.lp_solves += 1
            if res.status == 2:
                v, why = False, 'root-core'
            elif res.status == 0:
                self.root_z = np.array(res.x, copy=True)
        if v is None and self.yes_scan and self.root_z is not None:
            if self._yes_construct(self.root_z, self.yes_trials1,
                                   self.yes_nodecap1):
                v, why = True, 'yes-lp-small'
        if v is None and self.yes_scan and self.root_z is not None \
                and self.yes_nodes < self.yes_node_budget:
            if self._yes_construct(self.root_z, self.yes_trials2,
                                   self.yes_nodecap2):
                v, why = True, 'yes-lp'
        if v is None:
            self.budget = budget
            self.nodecap = self.nodes + nodecap
            try:
                v, why = self._search([(0, 1)] * self.lp.base.N, 0)
            except Budget:
                v, why = None, 'budget'
        return v, self._stats(why)

    def _stats(self, why):
        st = super()._stats(why)
        st.update(yes_scan=self.yes_scan, yes_calls=self.yes_calls,
                  yes_trials=self.yes_trials_used, yes_nodes=self.yes_nodes,
                  yes_ok=self.yes_ok, root_z=bool(self.root_z is not None),
                  recovered=self.recovered, forced_fail=self.forced_fail,
                  corrupt_caught=self.corrupt_caught,
                  corrupt_missed=self.corrupt_missed,
                  leaf_missing=self.leaf_missing, ft_splits=self.ft_splits,
                  ft_stuck=self.ft_stuck, ft_on=self.ft_on,
                  schedule=(None if self.schedule is None else
                            list(self.schedule)),
                  machine=(None if self.machine is None else
                           list(self.machine)))
        return st

    def audit_rdf(self):
        if not self.audit_qsp():
            return False
        if self.yes_ok and self.schedule is None:
            return False
        if self.schedule is not None:
            if not check_schedule(self.inst, self.h, self.schedule,
                                  self.machine):
                return False
        return True

    def proof_complete(self):
        """All NO facts have verified backing; no unbacked leaf/force.

        A missing leaf certificate that is replaced by a certified domain
        split is backed by its two children, so `leaf_missing` alone is not
        a failure; an unresolved missing cert (stuck/budget/FT off) is.
        """
        if self.ft_stuck > 0:
            return False
        if self.leaf_missing > self.ft_splits:
            return False
        for i, t, c in self.units:
            if not verify(self.inst, self.h, c, forbid={(i, t)},
                          elig_aware=self.elig):
                return False
        for i, allowed, E, c in self.force_events:
            if not verify(self.inst, self.h, c, forbid=E,
                          elig_aware=self.elig):
                return False
        return True
