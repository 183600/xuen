"""v6.2 PSS: Parametric Split Search with divide-and-conquer proof trees.

Builds on v6.1 ALC.  The new ingredient is the branching rule: instead of
splitting at the median of the chosen start-time variable, binary-search the
two monotone infeasibility thresholds of the child LPs.  If the thresholds
cross, both children are infeasible and the node closes with a three-node
proof; if they do not cross, one child can still be closed and only the other
is recursed into.

A proof is a tree whose leaves are integer Farkas certificates (or CP
conflicts) and whose internal nodes are start-time domain splits.  The tree
itself is auditable: every leaf is replayed exactly, and every split covers
the parent's integer start domain.
"""
import sys
import time
import random
import numpy as np

sys.path[:0] = ['exp/v62', 'exp/v61', 'exp/v60', 'exp/v13']
import cert as v60cert
from cert import integer_certificate_from_lp, verify
from lazy import LazySD
from po import heads_tails
from cp import cp_conflict, verify_cp


def _leaf(status, cert=None, forbid=None, reason=None, bounds=None,
          schedule=None):
    return dict(kind='leaf', status=status, cert=cert, forbid=set(forbid or ()),
                reason=reason, children=[], bounds=bounds,
                schedule=schedule)


def _split(i, mid, children, extra=None, bounds=None):
    d = dict(kind='split', status=None, cert=None, forbid=set(),
             reason=None, i=i, mid=mid, children=children, bounds=bounds)
    if extra:
        d.update(extra)
    return d


class PSS:
    def __init__(self, inst, h, cert_on=True, topk=100, max_rounds=60,
                 task_order='cheap', cp_on=True, cp_budget=None,
                 cp_seed=0, seed=0):
        self.inst = inst
        self.h = h
        self.n = inst['n']
        self.cert_on = cert_on
        self.topk = topk
        self.max_rounds = max_rounds
        self.task_order = task_order
        self.cp_on = cp_on
        self.cp_budget = cp_budget
        self.cp_seed = cp_seed
        self.seed = seed
        self.rng = random.Random(seed)
        self.elig_aware = any(len(set(inst['elig'][i])) < inst['m']
                              for i in range(self.n))
        self.lp = LazySD(inst, h, elig_aware=self.elig_aware)
        self.est, self.q = self.lp.est, self.lp.q
        self.nodes = 0
        self.lp_solves = 0
        self.cert_calls = 0
        self.cert_t = 0.0
        self.events = []
        self.proof = None
        self.cut_rounds = 0

    # ------------------------------------------------------------- domains
    def allowed_times(self, i, bounds):
        times = set()
        for key, c in self.lp.idx.items():
            if key[0] != i:
                continue
            if bounds[c] != (0, 0):
                times.add(key[-1])
        return sorted(times)

    def _forbid(self, bounds):
        f = set()
        for c, key in enumerate(self.lp.cols):
            if bounds[c] == (0, 0):
                f.add((key[0], key[-1]))
        return f

    def _bounds_for_mid(self, i, mid, side, bounds):
        out = list(bounds)
        for key, c in self.lp.idx.items():
            if key[0] != i:
                continue
            t = key[-1]
            if side == 'L' and t > mid:
                out[c] = (0, 0)
            elif side == 'R' and t <= mid:
                out[c] = (0, 0)
        return out

    # --------------------------------------------------------------- LP
    def _solve_rounds(self, bounds):
        last = None
        for rnd in range(self.max_rounds):
            res = self.lp.solve(bounds)
            self.lp_solves += 1
            last = res
            ev = dict(kind='lp', node=self.nodes, round=rnd,
                      status=('infeasible' if res.status == 2 else
                              ('feasible' if res.status == 0 else 'other')),
                      cuts=len(self.lp.cuts), lp=self.lp_solves)
            self.events.append(ev)
            if res.status != 0:
                self.cut_rounds += 1
                return res, None, rnd
            viol = self.lp.separate(res.x, topk=self.topk)
            if not viol:
                return res, res.x, rnd
            for _, i, j, t in viol:
                if (i, j, t) not in self.lp.cutset:
                    self.lp.cutset.add((i, j, t))
                    self.lp.cuts.append((i, j, t))
                    self.events.append(dict(kind='cut', node=self.nodes,
                                            cut=(i, j, t),
                                            cuts=len(self.lp.cuts),
                                            lp=self.lp_solves))
        return last, None, self.max_rounds

    def _extract(self, bounds):
        t0 = time.time()
        self.cert_calls += 1
        forbid = self._forbid(bounds)
        if forbid:
            # The child LP is the lazy LP with a subset of columns removed.
            # Rebuilding that smaller LP is much cheaper than falling back to
            # the full SDLP, and the certificate is still valid for the full
            # problem because all omitted columns are in `forbid`.
            lp2 = LazySD(self.inst, self.h, elig_aware=self.elig_aware,
                         forbid=forbid)
            lp2.cuts = list(self.lp.cuts)
            lp2.cutset = set(lp2.cuts)
            lp2.A, lp2.hi = lp2.matrix()
            c = integer_certificate_from_lp(lp2, self.inst, self.h)
            ok = c is not None and verify(self.inst, self.h, c,
                                          forbid=forbid,
                                          elig_aware=self.elig_aware)
            if not ok:
                c = v60cert.integer_certificate(self.inst, self.h,
                                                forbid=forbid,
                                                elig_aware=self.elig_aware)
                ok = c is not None and verify(self.inst, self.h, c,
                                              forbid=forbid,
                                              elig_aware=self.elig_aware)
        else:
            self.lp.A, self.lp.hi = self.lp.matrix()
            c = integer_certificate_from_lp(self.lp, self.inst, self.h)
            ok = c is not None and verify(self.inst, self.h, c,
                                          elig_aware=self.elig_aware)
        self.cert_t += time.time() - t0
        return c, ok, forbid

    # -------------------------------------------------------- parametric
    def _child_status(self, i, mid, side, bounds):
        b = self._bounds_for_mid(i, mid, side, bounds)
        res = self.lp.solve(b)
        self.lp_solves += 1
        return res.status

    def _parametric_split(self, i, bounds):
        times = self.allowed_times(i, bounds)
        mids = times[:-1]
        if not mids:
            return None, 0
        calls = 0

        def left_inf(mid):
            nonlocal calls
            calls += 1
            return self._child_status(i, mid, 'L', bounds) == 2

        def right_inf(mid):
            nonlocal calls
            calls += 1
            return self._child_status(i, mid, 'R', bounds) == 2

        # left-infeasible mids form a prefix; right-infeasible a suffix
        lo, hi = 0, len(mids) - 1
        lstar = None
        while lo <= hi:
            mm = (lo + hi) // 2
            if left_inf(mids[mm]):
                lstar = mids[mm]
                lo = mm + 1
            else:
                hi = mm - 1
        lo, hi = 0, len(mids) - 1
        rstar = None
        while lo <= hi:
            mm = (lo + hi) // 2
            if right_inf(mids[mm]):
                rstar = mids[mm]
                hi = mm - 1
            else:
                lo = mm + 1
        if lstar is not None and rstar is not None and rstar <= lstar:
            return dict(i=i, mid=rstar, times=times, cross=True,
                        left_inf=True, right_inf=True, calls=calls), calls
        # no crossing: pick a split that closes one side, preferring the
        # smaller remaining child (fewer allowed starts).
        cand = []
        if lstar is not None:
            left_size = sum(1 for t in times if t <= lstar)
            right_size = len(times) - left_size
            cand.append((right_size, lstar, True, False))
        if rstar is not None:
            left_size = sum(1 for t in times if t <= rstar)
            right_size = len(times) - left_size
            cand.append((left_size, rstar, False, True))
        if cand:
            cand.sort()
            _, mid, li, ri = cand[0]
        else:
            mid = mids[len(mids) // 2]
            li = ri = False
        return dict(i=i, mid=mid, times=times, cross=False,
                    left_inf=li, right_inf=ri, calls=calls), calls

    def _task_order(self, z, bounds):
        mass = [0.0] * self.n
        for c, key in enumerate(self.lp.cols):
            if bounds[c] == (0, 0):
                continue
            zz = z[c]
            if 1e-7 < zz < 1 - 1e-7:
                mass[key[0]] += min(zz, 1 - zz)
        tasks = [i for i in range(self.n) if mass[i] > 1e-9]
        if self.task_order == 'random':
            self.rng.shuffle(tasks)
        else:
            tasks.sort(key=lambda i: (len(self.allowed_times(i, bounds)),
                                      -mass[i], i))
        return tasks

    # ------------------------------------------------------------ search
    def _branch(self, bounds, depth):
        self.nodes += 1
        if self.cp_on:
            forb = self._forbid(bounds)
            cc = cp_conflict(self.inst, self.h, forbid=forb,
                             budget=self.cp_budget, seed=self.cp_seed)
            if cc is not None and verify_cp(self.inst, self.h, cc,
                                            forbid=forb):
                return _leaf(False, cc, forb, reason='cp', bounds=bounds)
        res, z, rnd = self._solve_rounds(bounds)
        if res.status == 2:
            if not self.cert_on:
                return _leaf(False, reason='no-cert', bounds=bounds)
            c, ok, forbid = self._extract(bounds)
            return _leaf(False, c if ok else None, forbid,
                         reason='farkas' if ok else 'cert-failed',
                         bounds=bounds)
        if z is None:
            return _leaf(None, reason='roundcap', bounds=bounds)
        frac = [c for c in range(self.lp.base.N)
                if bounds[c] != (0, 0) and 1e-7 < z[c] < 1 - 1e-7]
        if not frac:
            sched = self.lp.base.integral_solution(z)
            if sched is not None:
                return _leaf(True, reason='integer', bounds=bounds,
                             schedule=sched)
            return _leaf(None, reason='integral-but-invalid', bounds=bounds)
        order = self._task_order(z, bounds)
        chosen = None
        for i in order:
            sp, calls = self._parametric_split(i, bounds)
            if sp is None:
                continue
            if chosen is None:
                chosen = sp
            if sp['cross']:
                chosen = sp
                break
        if chosen is None:
            return _leaf(None, reason='no-split', bounds=bounds)
        i, mid = chosen['i'], chosen['mid']
        lb = self._bounds_for_mid(i, mid, 'L', bounds)
        rb = self._bounds_for_mid(i, mid, 'R', bounds)
        left = self._branch(lb, depth + 1) if not chosen['left_inf'] else None
        right = self._branch(rb, depth + 1) if not chosen['right_inf'] else None
        if chosen['left_inf']:
            c, ok, f = self._extract(lb)
            left = _leaf(False, c if ok else None, f,
                         reason='farkas' if ok else 'cert-failed',
                         bounds=lb)
        if chosen['right_inf']:
            c, ok, f = self._extract(rb)
            right = _leaf(False, c if ok else None, f,
                          reason='farkas' if ok else 'cert-failed',
                          bounds=rb)
        # A YES witness needs only one branch: a schedule in a subdomain is
        # a schedule in the parent.  Returning the YES leaf directly keeps
        # the certificate a single path instead of a full proof tree.
        if left['status'] is True:
            return left
        if right['status'] is True:
            return right
        node = _split(i, mid, [left, right], dict(
            cross=chosen['cross'], calls=chosen['calls'],
            depth=depth, left_inf=chosen['left_inf'],
            right_inf=chosen['right_inf']), bounds=bounds)
        if left['status'] is False and right['status'] is False:
            node['status'] = False
        else:
            node['status'] = None
        return node

    def decide(self):
        base = [(0, 1)] * self.lp.base.N
        self.nodes = 0
        root = self._branch(base, 0)
        self.proof = root
        return root['status'], dict(
            verdict=root['status'], nodes=self.nodes,
            lp_solves=self.lp_solves, cuts=len(self.lp.cuts),
            cert_calls=self.cert_calls, cert_t=self.cert_t,
            events=self.events, proof=root)


def verify_schedule(inst, h, sched, elig_aware=None):
    """Exact replay of an integer schedule leaf."""
    if sched is None:
        return False
    n, m, p = inst['n'], inst['m'], inst['p']
    if len(sched) != n:
        return False
    starts = [None] * n
    machines = [None] * n
    for i, item in enumerate(sched):
        if item is None:
            return False
        t, k = item
        if not (0 <= t <= h - p[i]):
            return False
        starts[i] = t
        machines[i] = k
    if elig_aware is None:
        elig_aware = any(len(set(inst['elig'][i])) < m for i in range(n))
    if elig_aware:
        for i, k in enumerate(machines):
            if k not in inst['elig'][i]:
                return False
    else:
        # interval coloring with m machines; total load <= m is sufficient
        order = sorted(range(n), key=lambda i: (starts[i], -p[i]))
        free = [0] * m
        for i in order:
            placed = False
            for k in range(m):
                if free[k] <= starts[i]:
                    free[k] = starts[i] + p[i]
                    machines[i] = k
                    placed = True
                    break
            if not placed:
                return False
    for i in range(n):
        for j in inst['succ'][i]:
            if starts[i] + p[i] > starts[j]:
                return False
        if starts[i] + p[i] + inst['p'][i] * 0 > h:
            return False
    for k in range(m):
        occ = []
        for i in range(n):
            if machines[i] != k:
                continue
            occ.append((starts[i], starts[i] + p[i], i))
        occ.sort()
        for a, b in zip(occ, occ[1:]):
            if a[1] > b[0]:
                return False
    return True


def verify_proof(inst, h, node, elig_aware=None):
    """Audit a proof tree: leaf certificates plus disjoint domain cover."""
    if node is None:
        return False
    if elig_aware is None:
        elig_aware = any(len(set(inst['elig'][i])) < inst['m']
                         for i in range(inst['n']))
    lp = LazySD(inst, h, elig_aware=elig_aware)
    N = lp.base.N
    n = inst['n']

    def allowed(i, bounds):
        return frozenset(key[-1] for key, c in lp.idx.items()
                         if key[0] == i and bounds[c] != (0, 0))

    def rec(nd):
        b = nd.get('bounds')
        if b is None or len(b) != N:
            return False
        if nd['kind'] == 'leaf':
            if nd['status'] is True:
                return verify_schedule(inst, h, nd.get('schedule'),
                                       elig_aware=elig_aware)
            if nd['status'] is not False or nd['cert'] is None:
                return False
            c = nd['cert']
            if c.get('kind') in ('empty', 'path', 'timetable', 'energy'):
                return verify_cp(inst, h, c, forbid=nd['forbid'])
            return verify(inst, h, c, forbid=nd['forbid'],
                          elig_aware=elig_aware)
        if nd['kind'] != 'split':
            return False
        if nd.get('status') is not False:
            return False
        i, mid = nd['i'], nd['mid']
        if len(nd['children']) != 2:
            return False
        lb = nd['children'][0].get('bounds')
        rb = nd['children'][1].get('bounds')
        if lb is None or rb is None or len(lb) != N or len(rb) != N:
            return False
        for c in range(N):
            if b[c] == (0, 0) and (lb[c] != (0, 0) or rb[c] != (0, 0)):
                return False
        for j in range(n):
            P = allowed(j, b)
            L = allowed(j, lb)
            R = allowed(j, rb)
            if j == i:
                EL = frozenset(t for t in P if t <= mid)
                ER = frozenset(t for t in P if t > mid)
                if L != EL or R != ER:
                    return False
            elif L != P or R != P:
                return False
        return rec(nd['children'][0]) and rec(nd['children'][1])

    return rec(node)


def count_leaves(node):
    if node is None:
        return 0, 0, 0
    if node['kind'] == 'leaf':
        return (1, 1 if node['status'] is False else 0,
                1 if node['status'] is True else 0)
    a = count_leaves(node['children'][0])
    b = count_leaves(node['children'][1])
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def depth(node):
    if node['kind'] == 'leaf':
        return 0
    return 1 + max(depth(node['children'][0]), depth(node['children'][1]))
