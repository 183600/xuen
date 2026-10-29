"""v9.1 PIVOT-ALC: P-core identification + greedy portfolio + vertex swarm.

Builds on v8.0 BRC-ALC.  The new layers are all *one-sided* or independently
verifiable:

  * P-core NO filters: critical-path, total-work and interval-energy lower
    bounds.  Each is a polynomial-time certificate; when it fires, the
    instance is NO without any LP.
  * Greedy YES portfolio: eight deterministic serial-SGS priority rules.
    A returned schedule is replayed by the independent checker.
  * Vertex swarm: ants are linear objectives; they share the lazy cut pool
    (stigmergy) and solve the start-time LP with their own objective.  An
    integral LP vertex is decoded to a schedule and replayed.
  * The v8.0 BRC SGS constructor remains as the bounded fallback, followed
    by the full certified NO search.

The P-core layers never claim NO without a replayable bound, and never claim
YES without a replayed schedule.  Consequently PIVOT is sound regardless of
how often the heuristics fire.
"""
import sys
import math
import numpy as np
from scipy.optimize import linprog

sys.path[:0] = ['exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from rdf import (RDF, check_schedule, _heads_latest, _insert, _earliest)
from po import heads_tails
from qnc import Budget
from sdecc import SDLP


# ------------------------------------------------------------- P-core bounds
def _windows(inst, h):
    n, p = inst['n'], inst['p']
    est, q = heads_tails(inst, 0, [0] * n)
    lst = [h - q[i] - p[i] for i in range(n)]
    return est, lst, q


def _machine_subsets(inst, max_subsets=64):
    m = inst['m']
    out = [frozenset(range(m))]
    if m <= 6:
        for mask in range(1, 1 << m):
            out.append(frozenset(k for k in range(m) if mask & (1 << k)))
    else:
        for k in range(m):
            out.append(frozenset({k}))
        for i in range(inst['n']):
            out.append(frozenset(inst['elig'][i]))
    seen, uniq = set(), []
    for M in out:
        if M and M not in seen:
            seen.add(M)
            uniq.append(M)
    return uniq[:max_subsets]


def prep_no_cert(inst, h, max_subsets=64, max_intervals=20000):
    """Return a replayable polynomial-time NO certificate, or None.

    Three independent lower bounds:
      cp     longest precedence path (est_i + p_i + tail_i)
      work   total processing volume / m
      energy interval [a,b) on a machine subset M (jobs eligible only on M)
    """
    n, m, p = inst['n'], inst['m'], inst['p']
    est, lst, q = _windows(inst, h)
    # critical path / empty window
    need = [est[i] + p[i] + q[i] for i in range(n)]
    i0 = max(range(n), key=lambda i: need[i])
    if need[i0] > h:
        return dict(kind='cp', job=i0, est=est[i0], p=p[i0], tail=q[i0],
                    need=need[i0], h=h)
    # total work
    demand = sum(p)
    if demand > m * h:
        return dict(kind='work', demand=demand, cap=m * h, h=h)
    # interval energy
    pts = sorted(set(est + [lst[i] + p[i] for i in range(n)]))
    pairs = [(0, h)] if h > 0 else []
    for ai, a in enumerate(pts):
        for b in pts[ai + 1:]:
            if b > a:
                pairs.append((a, b))
            if len(pairs) >= max_intervals:
                break
        if len(pairs) >= max_intervals:
            break
    for M in _machine_subsets(inst, max_subsets):
        js = [i for i in range(n) if set(inst['elig'][i]) <= M]
        if not js:
            continue
        cap = len(M)
        for a, b in pairs:
            if b <= a:
                continue
            dem = 0
            for i in js:
                dem += max(0, p[i] - max(0, a - est[i])
                           - max(0, lst[i] + p[i] - b))
            if dem > cap * (b - a):
                return dict(kind='energy', M=sorted(M), a=a, b=b,
                            jobs=js, demand=dem, cap=cap * (b - a), h=h)
    return None


def verify_prep(inst, h, cert):
    """Independent replay of a P-core NO certificate."""
    if not cert:
        return False
    n, m, p = inst['n'], inst['m'], inst['p']
    est, lst, q = _windows(inst, h)
    kind = cert.get('kind')
    if kind == 'cp':
        i = cert['job']
        return (0 <= i < n and cert['est'] == est[i]
                and cert['p'] == p[i] and cert['tail'] == q[i]
                and est[i] + p[i] + q[i] > h)
    if kind == 'work':
        return (cert['demand'] == sum(p)
                and cert['cap'] == m * h and sum(p) > m * h)
    if kind == 'energy':
        M = set(cert['M'])
        a, b = cert['a'], cert['b']
        if not M or a >= b:
            return False
        js = [i for i in range(n) if set(inst['elig'][i]) <= M]
        if js != list(cert['jobs']):
            return False
        dem = 0
        for i in js:
            dem += max(0, p[i] - max(0, a - est[i])
                       - max(0, lst[i] + p[i] - b))
        return (dem == cert['demand']
                and dem > len(M) * (b - a)
                and cert['cap'] == len(M) * (b - a))
    return False


# --------------------------------------------------------- greedy YES cores
GREEDY_RULES = ('est', 'latest', 'tail', 'spt', 'lpt', 'slack', 'crit', 'mix')


def greedy_schedule(inst, h, rule):
    """Deterministic serial SGS.  Returns a replayed schedule or None.

    This is a polynomial-time *sufficient* YES procedure: it may fail on a
    feasible instance, but it never returns an invalid schedule.
    """
    n, m, p = inst['n'], inst['m'], inst['p']
    est, q, latest = _heads_latest(inst, h)
    if rule == 'est':
        key = lambda i: (est[i], i)
    elif rule == 'latest':
        key = lambda i: (latest[i], i)
    elif rule == 'tail':
        key = lambda i: (-q[i], est[i], i)
    elif rule == 'spt':
        key = lambda i: (p[i], est[i], i)
    elif rule == 'lpt':
        key = lambda i: (-p[i], est[i], i)
    elif rule == 'slack':
        key = lambda i: (latest[i] - est[i], est[i], i)
    elif rule == 'crit':
        key = lambda i: (latest[i], -q[i], i)
    elif rule == 'mix':
        key = lambda i: (est[i] - 0.5 * q[i], i)
    else:
        raise ValueError(rule)
    starts = [None] * n
    machs = [None] * n
    busy = [[] for _ in range(m)]
    rem = [len(inst['pred'][i]) for i in range(n)]
    predfin = [0] * n
    done = [False] * n
    for _ in range(n):
        av = [i for i in range(n) if not done[i] and rem[i] == 0]
        if not av:
            return None
        av.sort(key=key)
        i = av[0]
        base = max(est[i], predfin[i])
        opts = []
        for k in inst['elig'][i]:
            t = _earliest(busy[k], base, p[i])
            if t <= latest[i]:
                opts.append((t, k))
        if not opts:
            return None
        t, k = min(opts)
        starts[i], machs[i] = t, k
        done[i] = True
        _insert(busy, k, t, t + p[i])
        for j in inst['succ'][i]:
            predfin[j] = max(predfin[j], t + p[i])
            rem[j] -= 1
    if check_schedule(inst, h, starts, machs):
        return starts, machs
    return None


# ------------------------------------------------------------- vertex swarm
def _objective(kind, seed, inst, lp):
    """An ant's linear objective over LP columns."""
    rng = np.random.default_rng(seed)
    N = getattr(lp, 'N', None)
    if N is None:
        N = lp.base.N
    n = inst['n']
    if kind == 'gauss':
        return rng.normal(size=N)
    if kind == 'unif':
        return rng.uniform(-1.0, 1.0, size=N)
    if kind == 'rad':
        return rng.choice([-1.0, 1.0], size=N)
    if kind == 'sparse':
        c = np.zeros(N)
        idx = rng.choice(N, size=max(1, N // 8), replace=False)
        c[idx] = rng.normal(size=len(idx))
        return c
    if kind == 'task':
        w = rng.normal(size=n)
        return np.array([w[key[0]] for key in lp.cols], dtype=float)
    if kind == 'time':
        return (np.array([key[-1] for key in lp.cols], dtype=float)
                + 0.5 * rng.normal(size=N))
    if kind == 'antitime':
        return (-np.array([key[-1] for key in lp.cols], dtype=float)
                + 0.5 * rng.normal(size=N))
    if kind == 'lp':
        # follow the current fractional solution, then perturb.
        z = np.asarray(lp._cache_z)
        return -z + 0.25 * rng.normal(size=N)
    raise ValueError(kind)


def _decode_full(inst, h, lp, z):
    """Decode an integral vertex of the full SD LP and replay it."""
    n, m, p = inst['n'], inst['m'], inst['p']
    starts = [None] * n
    machs = [None] * n
    for cc, key in enumerate(lp.cols):
        if z[cc] > 1 - 1e-7:
            i, t = key[0], key[-1]
            k = key[1] if len(key) > 2 else None
            if starts[i] is not None:
                return None
            starts[i] = t
            if k is not None:
                machs[i] = k
    if any(s is None for s in starts):
        return None
    if any(mk is None for mk in machs):
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
    if check_schedule(inst, h, starts, machs):
        return starts, machs
    return None


class PIVOT(RDF):
    def __init__(self, inst, h, prep_on=True, greedy_on=True, vertex_on=True,
                 vertex_trials=32, vertex_rounds=80, vertex_topk=100,
                 vertex_families=('sparse', 'sparse', 'unif', 'rad',
                                  'sparse', 'task', 'time', 'gauss'),
                 vertex_backend='full', vertex_seed=20261024,
                 greedy_rules=GREEDY_RULES, **kw):
        super().__init__(inst, h, **kw)
        self.prep_on = prep_on
        self.greedy_on = greedy_on
        self.vertex_on = vertex_on
        self.vertex_trials = vertex_trials
        self.vertex_rounds = vertex_rounds
        self.vertex_topk = vertex_topk
        self.vertex_families = tuple(vertex_families)
        self.vertex_backend = vertex_backend
        self.vertex_seed = vertex_seed
        self.greedy_rules = tuple(greedy_rules)
        self.prep_no = None
        self.greedy_rule = None
        self.vertex_lp = 0
        self.vertex_used = 0
        self.vertex_hits = 0
        self.vertex_frac = 0
        self.vertex_bad = 0
        self.vertex_done = False
        self.vertex_why = None
        self.full_lp = None

    # ------------------------------------------------------------ helpers
    def _greedy_portfolio(self):
        for rule in self.greedy_rules:
            got = greedy_schedule(self.inst, self.h, rule)
            if got is not None:
                self.schedule, self.machine = got
                self.yes_ok = True
                self.greedy_rule = rule
                return True
        return False

    def _lazy_vertex(self, c):
        """Solve LP(C; c), lazily add violated dominance rows, return z/status."""
        N = self.lp.base.N
        for _ in range(self.vertex_rounds):
            A, hi = self.lp.matrix()
            ne = self.lp.n_eq
            r = linprog(c, A_ub=A, b_ub=hi, A_eq=A[:ne],
                        b_eq=np.ones(self.n), bounds=[(0, 1)] * N,
                        method='highs')
            self.lp_solves += 1
            self.vertex_lp += 1
            if r.status != 0:
                return None, r.status
            viol = self.lp.separate(r.x, topk=self.vertex_topk)
            if not viol:
                return r.x, 0
            for _, i, j, t in viol:
                if (i, j, t) not in self.lp.cutset:
                    self.lp.cutset.add((i, j, t))
                    self.lp.cuts.append((i, j, t))
        return None, 'roundcap'

    def _vertex_swarm(self, z):
        """Stigmergic vertex search: shared constraints, independent objectives."""
        if not self.vertex_on or self.vertex_done:
            return False
        self.vertex_done = True
        if self.vertex_backend == 'full':
            return self._vertex_swarm_full()
        return self._vertex_swarm_lazy()

    def _vertex_swarm_full(self):
        n = self.n
        est, q = heads_tails(self.inst, 0, [0] * n)
        lp = SDLP(self.inst, self.h, est, q, use_dom=True,
                  elig_aware=self.elig)
        self.full_lp = lp
        fam = self.vertex_families
        for s in range(self.vertex_trials):
            self.vertex_used += 1
            kind = fam[s % len(fam)]
            c = _objective(kind, self.vertex_seed + 7919 * s, self.inst, lp)
            r = linprog(c, A_ub=lp.A, b_ub=lp.hi, A_eq=lp.A[:lp.n_eq],
                        b_eq=np.ones(n), bounds=[(0, 1)] * lp.N,
                        method='highs')
            self.lp_solves += 1
            self.vertex_lp += 1
            if r.status != 0:
                self.vertex_why = r.status
                continue
            if any(1e-7 < x < 1 - 1e-7 for x in r.x):
                self.vertex_frac += 1
                continue
            got = _decode_full(self.inst, self.h, lp, r.x)
            if got is None:
                self.vertex_bad += 1
                continue
            if check_schedule(self.inst, self.h, got[0], got[1]):
                self.schedule, self.machine = got
                self.yes_ok = True
                self.vertex_hits += 1
                return True
            self.vertex_bad += 1
        return False

    def _vertex_swarm_lazy(self):
        fam = self.vertex_families
        for s in range(self.vertex_trials):
            self.vertex_used += 1
            kind = fam[s % len(fam)]
            c = _objective(kind, self.vertex_seed + 7919 * s,
                           self.inst, self.lp)
            zz, why = self._lazy_vertex(c)
            if zz is None:
                self.vertex_why = why
                continue
            if any(1e-7 < x < 1 - 1e-7 for x in zz):
                self.vertex_frac += 1
                continue
            got = self._schedule_from_z(zz)
            if got is None:
                self.vertex_bad += 1
                continue
            if check_schedule(self.inst, self.h, got[0], got[1]):
                self.schedule, self.machine = got
                self.yes_ok = True
                self.vertex_hits += 1
                return True
            self.vertex_bad += 1
        return False

    # ------------------------------------------------------------- decide
    def decide(self, budget=100000, nodecap=5000, max_rounds=60, topk=100):
        if self.prep_on:
            cert = prep_no_cert(self.inst, self.h)
            if cert is not None:
                self.prep_no = cert
                return False, self._stats('prep-' + cert['kind'])
        if self.yes_scan and self.greedy_on:
            if self._greedy_portfolio():
                return True, self._stats('greedy-' + self.greedy_rule)
        return super().decide(budget=budget, nodecap=nodecap,
                              max_rounds=max_rounds, topk=topk)

    def _yes_construct(self, z, trials, nodecap):
        if not self.vertex_done:
            if self._vertex_swarm(z):
                return True
        return super()._yes_construct(z, trials, nodecap)

    # -------------------------------------------------------------- audit
    def _stats(self, why):
        st = super()._stats(why)
        st.update(prep_no=self.prep_no, prep_kind=(
            None if self.prep_no is None else self.prep_no.get('kind')),
            greedy_rule=self.greedy_rule, vertex_lp=self.vertex_lp,
            vertex_used=self.vertex_used, vertex_hits=self.vertex_hits,
            vertex_frac=self.vertex_frac, vertex_bad=self.vertex_bad,
            vertex_why=self.vertex_why, vertex_backend=self.vertex_backend)
        return st

    def audit_pivot(self):
        if self.prep_no is not None:
            if not verify_prep(self.inst, self.h, self.prep_no):
                return False
        if not self.audit_rdf():
            return False
        if self.yes_ok and self.schedule is None:
            return False
        if self.schedule is not None:
            if not check_schedule(self.inst, self.h, self.schedule,
                                  self.machine):
                return False
        return True

    def proof_complete(self):
        if self.prep_no is not None:
            return verify_prep(self.inst, self.h, self.prep_no)
        return super().proof_complete()
