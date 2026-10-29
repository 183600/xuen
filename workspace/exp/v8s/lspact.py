"""v9.0 LSPACT: Fenwick local search + PACT certificate trees.

LSPACT keeps PACT-ALC's bracket, complete NO search and TotalTrace.  It
adds a primal local-search layer on the yes side:

  * LS-SCHED: a min-conflicts search over start times and machines.  Each
    machine has a Fenwick tree of occupied slots; moving a job is a range
    update and an overlap query is a prefix-sum query.  The search starts
    from a serial-SGS schedule, repairs horizon/precedence/machine
    conflicts, and returns only a schedule that passes check_schedule.
  * ROOT-FIRST probing: solve the root LP.  If it is already infeasible,
    return the Farkas NO; if the root is fractional, try LS before the
    complete PACT tree.  Only when LS fails does the exponential tree run.
  * LS never prunes a NO state.  It can only emit a verified YES.

The design is deliberately one-sided: the exponential certificate search
is still the only source of NO, but the deep YES side no longer has to
follow the LP branch path.
"""
import sys
import time
import random

sys.path[:0] = ['exp/v8s', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from pact import PACT, pact_decide, run_pact
from cab import _greedy_rank
from po import heads_tails
from rdf import check_schedule


class Fenwick:
    """Range-add / prefix-sum Fenwick tree over a bounded time horizon."""
    __slots__ = ('n', 'bit')

    def __init__(self, n):
        self.n = n
        self.bit = [0] * (n + 2)

    def _add(self, pos, val):
        i = pos + 1
        n = self.n
        bit = self.bit
        while i <= n:
            bit[i] += val
            i += i & -i

    def range_add(self, lo, hi, val):
        if lo >= hi:
            return
        self._add(lo, val)
        if hi < self.n:
            self._add(hi, -val)

    def point(self, pos):
        i = pos + 1
        s = 0
        bit = self.bit
        while i > 0:
            s += bit[i]
            i -= i & -i
        return s

    def prefix(self, pos):
        """Sum over [0, pos)."""
        i = pos
        s = 0
        bit = self.bit
        while i > 0:
            s += bit[i]
            i -= i & -i
        return s


class Profile:
    """Per-machine occupancy profile with Fenwick range updates."""
    __slots__ = ('m', 'h', 'load', 'occ', 'free')

    def __init__(self, m, h):
        self.m = m
        self.h = h
        self.load = [Fenwick(h) for _ in range(m)]
        self.occ = [Fenwick(h) for _ in range(m)]
        self.free = [Fenwick(h) for _ in range(m)]

    def add(self, k, lo, hi, delta):
        if lo >= hi:
            return
        self.load[k].range_add(lo, hi, delta)
        # occupancy indicator and free-slot counts
        for t in range(lo, hi):
            before = self.occ[k].point(t)
            after = before + delta
            if before == 0 and after > 0:
                self.occ[k].range_add(t, t + 1, 1)
                self.free[k].range_add(t, t + 1, -1)
            elif before > 0 and after == 0:
                self.occ[k].range_add(t, t + 1, -1)
                self.free[k].range_add(t, t + 1, 1)

    def init_free(self):
        for k in range(self.m):
            self.free[k].range_add(0, self.h, 1)

    def occupied(self, k, lo, hi):
        return self.occ[k].prefix(hi) - self.occ[k].prefix(lo)


def _domains(inst, h, forbid=None):
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    latest = [h - q[i] - inst['p'][i] for i in range(n)]
    out = []
    for i in range(n):
        if latest[i] < est[i]:
            return None
        ds = [t for t in range(est[i], latest[i] + 1)
              if forbid is None or (i, t) not in forbid]
        if not ds:
            return None
        out.append(ds)
    return out, est, latest


def _sgs_init(inst, h, rng, tries=24, forbid=None):
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    latest = [h - q[i] - inst['p'][i] for i in range(n)]
    best = None
    bc = 10 ** 9
    for _ in range(tries):
        rank = {}
        for i in range(n):
            if rng.random() < 0.5:
                rank[i] = latest[i] + rng.random() * 1e-6
            else:
                rank[i] = est[i] + rng.random() * 1e-6
        g = _greedy_rank(inst, rank)
        if g is not None and g[2] < bc:
            best, bc = g, g[2]
    return best


def ls_schedule(inst, h, budget=1600, seed=0, restarts=2, forbid=None):
    """Min-conflicts local search; returns a verified (starts, machines)."""
    t0 = time.time()
    n, m, p = inst['n'], inst['m'], inst['p']
    dom = _domains(inst, h, forbid)
    if dom is None:
        return None, dict(iters=0, restarts=0, t=0.0, init=None)
    domains, est, latest = dom
    pred, succ, elig = inst['pred'], inst['succ'], inst['elig']
    rng = random.Random(20261025 + seed * 100003)

    def energy(s, mk, prof):
        e = 0
        for i in range(n):
            if s[i] + p[i] > h:
                e += s[i] + p[i] - h
            for j in succ[i]:
                d = s[i] + p[i] - s[j]
                if d > 0:
                    e += d
        for k in range(m):
            for t in range(h):
                v = prof.load[k].point(t)
                if v > 1:
                    e += v - 1
        return e

    best_all = None
    best_e = 10 ** 9
    used = 0
    for run in range(restarts):
        g = _sgs_init(inst, h, rng, forbid=forbid)
        if g is None:
            continue
        s, mk, c = g
        s, mk = list(s), list(mk)
        if c <= h and check_schedule(inst, h, s, mk):
            return (s, mk), dict(iters=used, restarts=run + 1,
                                 t=time.time() - t0, init='sgs')
        TT = max([h] + [s[i] + p[i] for i in range(n)])
        prof = Profile(m, TT)
        prof.init_free()
        for i in range(n):
            prof.add(mk[i], s[i], s[i] + p[i], 1)
        E = energy(s, mk, prof)
        if E < best_e:
            best_e, best_all = E, (s[:], mk[:])
        tabu = {}
        for it in range(budget):
            used += 1
            if E == 0:
                if check_schedule(inst, h, s, mk):
                    return (s, mk), dict(iters=used, restarts=run + 1,
                                         t=time.time() - t0, init='sgs')
                E = energy(s, mk, prof)
            bad = set()
            for i in range(n):
                if s[i] + p[i] > h:
                    bad.add(i)
                for j in succ[i]:
                    if s[i] + p[i] > s[j]:
                        bad.add(i)
                        bad.add(j)
            for k in range(m):
                js = sorted([i for i in range(n) if mk[i] == k],
                            key=lambda i: s[i])
                for a, b in zip(js, js[1:]):
                    if s[a] + p[a] > s[b]:
                        bad.add(a)
                        bad.add(b)
            if not bad:
                bad = set(range(n))
            i = rng.choice(tuple(bad))
            os_, om = s[i], mk[i]

            def delta(t, k):
                d = 0
                if t + p[i] > h:
                    d += t + p[i] - h
                if os_ + p[i] > h:
                    d -= os_ + p[i] - h
                for j in pred[i]:
                    d -= max(0, s[j] + p[j] - os_)
                    d += max(0, s[j] + p[j] - t)
                for j in succ[i]:
                    d -= max(0, os_ + p[i] - s[j])
                    d += max(0, t + p[i] - s[j])
                # removal from old machine: each slot of load >= 2 loses 1
                for u in range(os_, min(TT, os_ + p[i])):
                    d -= 1 if prof.load[om].point(u) >= 2 else 0
                # insertion on new machine: each occupied slot gains 1
                for u in range(t, min(TT, t + p[i])):
                    v = prof.load[k].point(u)
                    if k == om and os_ <= u < os_ + p[i]:
                        v -= 1
                    d += 1 if v >= 1 else 0
                return d

            cands = []
            for t in domains[i]:
                for k in elig[i]:
                    if t == os_ and k == om:
                        continue
                    if tabu.get(i) == (t, k):
                        continue
                    cands.append((delta(t, k), rng.random(), t, k))
            if not cands:
                continue
            cands.sort(key=lambda x: (x[0], x[1]))
            d, _, t, k = cands[0]
            if d <= 0 or rng.random() < 0.02:
                tabu[i] = (os_, om)
                prof.add(om, os_, os_ + p[i], -1)
                prof.add(k, t, t + p[i], 1)
                s[i], mk[i] = t, k
                E += d
                if E < best_e:
                    best_e, best_all = E, (s[:], mk[:])
        if best_e == 0:
            s, mk = best_all
            if check_schedule(inst, h, s, mk):
                return (s, mk), dict(iters=used, restarts=run + 1,
                                     t=time.time() - t0, init='sgs')
    return None, dict(iters=used, restarts=restarts,
                      t=time.time() - t0, init='sgs', best=best_e)


class LSPACT(PACT):
    def __init__(self, inst, ls_budget=1600, ls_restarts=2,
                 ls_on=True, **kw):
        super().__init__(inst, **kw)
        self.ls_budget = ls_budget
        self.ls_restarts = ls_restarts
        self.ls_on = ls_on
        self.ls_calls = 0
        self.ls_yes = 0
        self.ls_no = 0
        self.ls_iters = 0
        self.ls_time = 0.0
        self.stats.update(ls_calls=0, ls_yes=0, ls_no=0, ls_iters=0)

    def _probe(self, h):
        if not self.ls_on:
            return super()._probe(h)
        # Root LP first: preserve the cheap k=0 NO and integral YES.
        r0 = pact_decide(self.inst, h, depthcap=0)
        self.pact_lp += r0['lp_solves']
        self.pact_cert_lp += r0.get('cert_lp', 0)
        self.pact_nodes += r0['nodes']
        if r0['verdict'] is False:
            self.pact_no += 1
            self.stats['pact_no'] += 1
            self._record_proof(r0['proof'])
            self.steps.append(dict(h=h, v=False, proof=r0['proof'],
                                   engine='root-lp'))
            return False, r0['proof']
        if r0['verdict'] is True:
            self.pact_yes += 1
            self.stats['pact_yes'] += 1
            s, m = r0['schedule'], r0['machine']
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine='root-lp'))
            return True, (s, m, cmax)
        # Root is fractional: spend the local-search budget before the tree.
        self.ls_calls += 1
        self.stats['ls_calls'] += 1
        got, st = ls_schedule(self.inst, h, budget=self.ls_budget,
                              seed=self.ls_calls + h,
                              restarts=self.ls_restarts)
        self.ls_iters += st['iters']
        self.stats['ls_iters'] += st['iters']
        self.ls_time += st['t']
        if got is not None:
            s, m = got
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            if check_schedule(self.inst, cmax, s, m):
                self.ls_yes += 1
                self.stats['ls_yes'] += 1
                self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                       cmax=cmax, engine='ls'))
                return True, (s, m, cmax)
        self.ls_no += 1
        self.stats['ls_no'] += 1
        # Fall back to the complete PACT tree.
        r = pact_decide(self.inst, h, depthcap=None, nodecap=None)
        self.pact_lp += r['lp_solves']
        self.pact_cert_lp += r.get('cert_lp', 0)
        self.pact_nodes += r['nodes']
        if r['verdict'] is False:
            self.pact_no += 1
            self.stats['pact_no'] += 1
            self._record_proof(r['proof'])
            self.steps.append(dict(h=h, v=False, proof=r['proof'],
                                   engine='complete'))
            return False, r['proof']
        if r['verdict'] is True:
            self.pact_yes += 1
            self.stats['pact_yes'] += 1
            s, m = r['schedule'], r['machine']
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine='complete'))
            return True, (s, m, cmax)
        self.stats['chd_fallback'] += 1
        v, st2, rdf = self._decide(h)
        self.queries += 1
        self._absorb(st2)
        self._record(h, v, st2)
        if v is False:
            self.steps.append(dict(h=h, v=False, proof=rdf, engine='chd'))
        elif v is True:
            s, m = rdf.schedule, rdf.machine
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine='chd'))
        else:
            self.steps.append(dict(h=h, v=None, engine='chd'))
        return v, rdf

    def _result(self):
        r = super()._result()
        r['ls_calls'] = self.ls_calls
        r['ls_yes'] = self.ls_yes
        r['ls_no'] = self.ls_no
        r['ls_iters'] = self.ls_iters
        r['ls_time'] = round(self.ls_time, 4)
        return r


def run_lspact(inst, known, name, idx, **kw):
    t0 = time.time()
    co = LSPACT(inst, **kw)
    r = co.optimize()
    dt = time.time() - t0
    r.update(name=name, idx=idx, known=known, t=round(dt, 4))
    b = getattr(co, 'chip', None) or {}
    p = getattr(co, 'pin', None) or {}
    r['chip_lb'] = b.get('lb')
    r['chip_ub'] = b.get('ub')
    r['pin_lb'] = p.get('lb')
    r['pin_solves'] = p.get('solves')
    r['pin_lp'] = getattr(co, 'pin_lp', 0)
    r['bb_lp'] = getattr(co, 'bb_lp', 0)
    r['cert_lp'] = getattr(co, 'cert_lp_total', 0)
    r['ga_stats'] = getattr(co, 'ga_stats', [])
    r['proof_kind'] = getattr(getattr(co, 'lb_proof', None),
                              'kind', None)
    r['stats2'] = getattr(co, 'stats', {})
    r['lns'] = getattr(co, 'lns_stats', None)
    r['ok'] = bool(r['certified'] and r['opt'] == known
                   and r['audit'] and r['proof'] and r['total_audit']
                   and r['cert_h'] == known - 1)
    return r
