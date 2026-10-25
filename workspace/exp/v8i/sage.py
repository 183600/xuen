"""v8.8 SAGE-ALC: self-stabilizing proof algebra + genetic upper repair.

SAGE keeps APEX's LP value function L* and its proof store, and adds a
third source of certified facts between "cheap bound" and "CHD oracle":

  * LP-BRANCH: a self-stabilizing refinement of the fixed-h SD LP.
    A fractional state is repaired by a domain split; the stable leaves
    are either integral schedules (YES) or Farkas leaves (NO).  A NO tree
    is an independently replayable proof of NO(h), so it enters the proof
    store without a CHD query.
  * GENETIC-UB: a memetic search over serial-SGS priority permutations.
    crossover (OX), mutation, elitism and a monotone local repair produce
    a verified schedule at the current lower bound; only schedules that
    pass check_schedule are accepted.
  * STAB: a monotone closure of the judgements NO/LB/UB/EXACT.  Iterating
    the subsumption rules to a fixed point makes the final certificate
    independent of the insertion order and removes the final "ask at
    OPT-1" step whenever a lower-bound proof already exists.

The outer loop is APEX's: LP pin, incumbent, small-bracket scan, CHD as
the last-resort oracle.  CHD is counted in Q; LP-BRANCH and GENETIC-UB
are counted separately (LP solves and SGS evaluations).
"""
import sys
import time
import random
import math

sys.path[:0] = ['exp/v8i', 'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g',
                'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a',
                'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60',
                'exp/v13']

import numpy as np

from apex import APEX, Proof
from chip import chip_bounds
from cab import _greedy_rank
from rdf import check_schedule
from cert import verify, integer_certificate
from sdecc import SDLP
from po import heads_tails


# ------------------------------------------------------------------ helpers
def _elig_aware(inst):
    return any(len(set(inst['elig'][i])) < inst['m']
               for i in range(inst['n']))


def _domain(inst, h, i):
    est, q = heads_tails(inst, 0, [0] * inst['n'])
    return est[i], h - q[i] - inst['p'][i]


# ------------------------------------------------------------- LP-BRANCH
class BranchProof(Proof):
    """A replayable NO(h) proof: a tree of domain splits with Farkas leaves."""

    kind = 'branch'

    def __init__(self, inst, h, tree, stats=None, forbid0=None):
        super().__init__(inst, h)
        self.tree = tree
        self.stats = stats or {}
        self.forbid0 = frozenset(forbid0 or ())

    def _allowed(self, i, F):
        lo, hi = _domain(self.inst, self.h, i)
        return [t for t in range(lo, hi + 1) if (i, t) not in F]

    def _check(self, node, F):
        tag = node[0]
        if tag == 'leaf':
            if set(node[1]) != set(F):
                return False
            cert = node[2]
            if cert.get('kind') == 'empty':
                return not self._allowed(cert['job'], F)
            return bool(verify(self.inst, self.h, cert, forbid=F))
        if tag == 'empty':
            return not self._allowed(node[2], F)
        _, i, mid, parent_F, lo, hi = node
        if set(parent_F) != set(F):
            return False
        allowed = self._allowed(i, F)
        lo_t = [t for t in allowed if t > mid]
        hi_t = [t for t in allowed if t <= mid]
        if not lo_t or not hi_t:
            return False
        loF = F | {(i, t) for t in lo_t}
        hiF = F | {(i, t) for t in hi_t}
        return self._check(lo, loF) and self._check(hi, hiF)

    def audit_rdf(self):
        try:
            return self._check(self.tree, self.forbid0)
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


class SubsumptionProof(Proof):
    """NO(h) derived from a stronger NO(h') with h' >= h (LB-NO)."""

    kind = 'lb-no'

    def __init__(self, inst, h, source):
        super().__init__(inst, h)
        self.source = source

    def audit_rdf(self):
        return bool(self.source is not None
                    and self.source.h >= self.h
                    and self.source.audit_rdf())

    def proof_complete(self):
        return bool(self.audit_rdf() and self.source.proof_complete())


def lp_branch_decide(inst, h, nodecap=96, depthcap=24, policy=None,
                     seed=0):
    """Self-stabilizing fixed-h LP refinement.

    Returns dict(verdict, proof, schedule, machine, nodes, leaves, depth,
    lp_solves, t).  verdict is False (NO with proof), True (YES with a
    checked schedule), or None (budget exhausted; caller asks CHD).
    """
    t0 = time.time()
    n, m, p = inst['n'], inst['m'], inst['p']
    elig = _elig_aware(inst)
    est, q = heads_tails(inst, 0, [0] * n)
    lp = SDLP(inst, h, est, q, use_dom=True, elig_aware=elig)
    base = [(0, 1)] * lp.N
    stats = dict(nodes=0, leaves=0, depth=0, lp_solves=0,
                 cert_lp=0, branch_jobs=[], unknown=False)
    policy = policy or {}

    def solve(bounds):
        stats['nodes'] += 1
        stats['lp_solves'] += 1
        if stats['nodes'] > nodecap:
            stats['unknown'] = True
            return None
        return lp.solve(bounds)

    def allowed_times(i, bounds):
        out = set()
        for c, key in enumerate(lp.cols):
            if key[0] == i and bounds[c] != (0, 0):
                out.add(key[-1])
        return sorted(out)

    def job_mass(z, i, times, bounds):
        mass = 0.0
        dist = []
        for tt in times:
            v = 0.0
            for c, key in enumerate(lp.cols):
                if key[0] == i and key[-1] == tt and bounds[c] != (0, 0):
                    v += z[c]
            dist.append((tt, v))
            mass += v
        return mass, dist

    def choose(z, bounds):
        cand = []
        for i in range(n):
            times = allowed_times(i, bounds)
            if len(times) <= 1:
                continue
            mass, dist = job_mass(z, i, times, bounds)
            frac = 0.0
            for tt, v in dist:
                if 1e-7 < v < 1 - 1e-7:
                    frac += v
            if frac <= 1e-7:
                continue
            slack = h - q[i] - p[i] - est[i]
            score = (mass, self_tail(q, i), len(inst['succ'][i]), -i)
            if policy.get('mode') == 'ga':
                score = (policy['wf'] * frac
                         + policy['wq'] * q[i]
                         + policy['wp'] * p[i]
                         + policy['ws'] * slack
                         + policy['wd'] * len(inst['succ'][i])
                         + policy['wr'] * ((i * 1103515245 + seed * 12345)
                                            % 1000) / 1000.0, -i)
            cand.append((score, i, dist))
        if not cand:
            return None, None
        cand.sort(reverse=True)
        _, i, dist = cand[0]
        total = sum(v for _, v in dist)
        split = policy.get('split', 0.5)
        acc = 0.0
        mid = dist[0][0]
        for tt, v in dist:
            acc += v
            if acc >= split * total:
                mid = tt
                break
        times = [tt for tt, _ in dist]
        lo_t = [tt for tt in times if tt > mid]
        hi_t = [tt for tt in times if tt <= mid]
        if not lo_t or not hi_t:
            mid = times[len(times) // 2 - 1] if len(times) > 1 else times[0]
            lo_t = [tt for tt in times if tt > mid]
            hi_t = [tt for tt in times if tt <= mid]
        if not lo_t or not hi_t:
            return None, None
        return i, mid

    def bound_side(bounds, i, mid, side):
        b = list(bounds)
        for c, key in enumerate(lp.cols):
            if key[0] != i:
                continue
            tt = key[-1]
            if (side == 'lo' and tt > mid) or (side == 'hi' and tt <= mid):
                b[c] = (0, 0)
        return b

    def leaf_cert(F):
        stats['cert_lp'] += 1
        cert = integer_certificate(inst, h, use_dom=True,
                                   elig_aware=elig, forbid=F)
        if cert is not None and verify(inst, h, cert, forbid=F):
            return ('leaf', frozenset(F), cert)
        # empty-domain leaf
        for i in range(n):
            lo, hi = _domain(inst, h, i)
            if lo <= hi and all((i, t) in F for t in range(lo, hi + 1)):
                return ('empty', frozenset(F), i)
        return None

    def integral_schedule(z):
        starts = [None] * n
        machs = [None] * n
        for c, key in enumerate(lp.cols):
            if z[c] > 1 - 1e-7:
                i, t = key[0], key[-1]
                if starts[i] is not None:
                    return None
                starts[i] = t
                if elig:
                    machs[i] = key[1]
        if any(x is None for x in starts):
            return None
        if not elig:
            busy = [[] for _ in range(m)]
            for i in sorted(range(n), key=lambda i: (starts[i], i)):
                for k in inst['elig'][i]:
                    if all(starts[i] + p[i] <= a or starts[i] >= b
                           for a, b in busy[k]):
                        machs[i] = k
                        busy[k].append((starts[i], starts[i] + p[i]))
                        break
                if machs[i] is None:
                    return None
        cmax = max(starts[i] + p[i] for i in range(n))
        if check_schedule(inst, cmax, starts, machs):
            return starts, machs
        return None

    def dfs(bounds, F, depth):
        if depth > depthcap:
            stats['unknown'] = True
            return None
        res = solve(bounds)
        if res is None:
            return None
        if res.status == 2:
            stats['leaves'] += 1
            node = leaf_cert(F)
            if node is None:
                stats['unknown'] = True
            return node
        if res.status != 0:
            stats['unknown'] = True
            return None
        z = res.x
        frac = False
        for c, key in enumerate(lp.cols):
            if 1e-7 < z[c] < 1 - 1e-7 and bounds[c] != (0, 0):
                frac = True
                break
        if not frac:
            got = integral_schedule(z)
            if got is None:
                stats['unknown'] = True
                return None
            return ('yes', got[0], got[1])
        i, mid = choose(z, bounds)
        if i is None:
            stats['unknown'] = True
            return None
        stats['depth'] = max(stats['depth'], depth)
        stats['branch_jobs'].append((i, mid))
        times = allowed_times(i, bounds)
        lo_t = [t for t in times if t > mid]
        hi_t = [t for t in times if t <= mid]
        loF = F | {(i, t) for t in lo_t}
        hiF = F | {(i, t) for t in hi_t}
        lo = dfs(bound_side(bounds, i, mid, 'lo'), loF, depth + 1)
        if lo is None:
            return None
        if lo[0] == 'yes':
            return lo
        hi = dfs(bound_side(bounds, i, mid, 'hi'), hiF, depth + 1)
        if hi is None:
            return None
        if hi[0] == 'yes':
            return hi
        return ('node', i, mid, frozenset(F), lo, hi)

    tree = dfs(base, frozenset(), 0)
    stats['t'] = round(time.time() - t0, 5)
    if tree is None:
        return dict(verdict=None, proof=None, schedule=None, machine=None,
                    **stats)
    if tree[0] == 'yes':
        return dict(verdict=True, proof=None, schedule=tree[1],
                    machine=tree[2], **stats)
    proof = BranchProof(inst, h, tree, stats)
    if not proof.audit_rdf():
        stats['unknown'] = True
        return dict(verdict=None, proof=None, schedule=None, machine=None,
                    **stats)
    return dict(verdict=False, proof=proof, schedule=None, machine=None,
                **stats)


def self_tail(q, i):
    return q[i]


# ------------------------------------------------------------- GENETIC-UB
def _ga_eval(inst, perm):
    rank = {perm[k]: k + 1e-7 * ((perm[k] * 7919) % 101)
            for k in range(len(perm))}
    g = _greedy_rank(inst, rank)
    if g is None:
        return (10 ** 9, 10 ** 9), None
    s, m, c = g
    return (c, sum(s[i] + inst['p'][i] for i in range(inst['n']))), (s, m)


def _ox(p1, p2, rng):
    n = len(p1)
    a = rng.randrange(n)
    b = rng.randrange(a, n)
    child = [None] * n
    child[a:b] = p1[a:b]
    used = set(child[a:b])
    pos = b % n
    for x in p2[b:] + p2[:b]:
        if x not in used:
            child[pos] = x
            pos = (pos + 1) % n
            used.add(x)
    return child


def _mutate(p, rng):
    q = list(p)
    n = len(q)
    if n < 2:
        return q
    a, b = rng.sample(range(n), 2)
    if rng.random() < 0.5:
        q[a], q[b] = q[b], q[a]
    else:
        x = q.pop(a)
        q.insert(b, x)
    return q


def _ga_local(inst, perm, passes, cache, used, budget):
    best, bf = perm, _ga_eval(inst, perm)[0]
    n = len(best)
    for _ in range(passes):
        improved = False
        for a in range(n):
            if budget[0] <= 0:
                return best, bf
            for b in range(a + 1, n):
                q = list(best)
                q[a], q[b] = q[b], q[a]
                key = tuple(q)
                if key not in cache:
                    cache[key] = _ga_eval(inst, q)
                    used[0] += 1
                    budget[0] -= 1
                f = cache[key][0]
                if f < bf:
                    best, bf = q, f
                    improved = True
                if budget[0] <= 0:
                    return best, bf
        if not improved:
            break
    return best, bf


def ga_schedule(inst, h, pop=40, gens=60, budget=4000, seed=0,
                local_passes=4):
    """Memetic search for a verified schedule at horizon h.

    Genome = job permutation; decoder = serial SGS; fitness =
    (makespan, sum completion); local repair accepts only strict
    improvements.  The returned schedule must pass check_schedule.
    """
    t0 = time.time()
    rng = random.Random(20261024 + seed * 100003)
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    latest = [h - q[i] - inst['p'][i] for i in range(n)]
    seeds = []
    for key in (lambda i: est[i], lambda i: latest[i],
                lambda i: -q[i],
                lambda i: est[i] - 0.5 * q[i]):
        seeds.append(sorted(range(n), key=lambda i: (key(i), i)))
    P = list(seeds)
    while len(P) < pop:
        a = list(range(n))
        rng.shuffle(a)
        P.append(a)
    cache = {}
    used = [0]
    for p in P:
        if tuple(p) not in cache:
            cache[tuple(p)] = _ga_eval(inst, p)
            used[0] += 1
    def score(p):
        return cache[tuple(p)][0]
    bestp = min(P, key=score)
    bestf = cache[tuple(bestp)][0]
    gens_used = 0
    for _ in range(gens):
        if bestf[0] <= h or used[0] >= budget:
            break
        gens_used += 1
        P.sort(key=score)
        new = P[:4]
        while len(new) < pop:
            a = rng.choice(P[:max(8, pop // 2)])
            b = rng.choice(P[:max(8, pop // 2)])
            child = _ox(a, b, rng)
            if rng.random() < 0.7:
                child = _mutate(child, rng)
            if rng.random() < 0.15 and used[0] < budget:
                child, _ = _ga_local(inst, child, 2, cache, used,
                                       [min(120, max(0, budget - used[0]))])
            if tuple(child) not in cache:
                cache[tuple(child)] = _ga_eval(inst, child)
                used[0] += 1
            new.append(child)
        P = new
        cp = min(P, key=score)
        cf = cache[tuple(cp)][0]
        if cf < bestf:
            bestp, bestf = cp, cf
    bestp, bestf = _ga_local(inst, bestp, local_passes, cache, used,
                              [min(2000, max(0, budget - used[0]))])
    got = cache.get(tuple(bestp))
    stats = dict(evals=used[0], gens=gens_used,
                 t=round(time.time() - t0, 5), best=bestf[0])
    if got is None:
        return None, stats
    s, m = got[1]
    cmax = max(s[i] + inst['p'][i] for i in range(n))
    if cmax <= h and check_schedule(inst, h, s, m):
        return (s, m), stats
    return None, stats


# ------------------------------------------------------------------- SAGE
class SAGE(APEX):
    def __init__(self, inst, bb_nodecap=96, bb_depthcap=24,
                 ga_budget=4000, ga_pop=40, ga_gens=60,
                 use_bb=True, use_ga=True, bb_yes=True, **kw):
        super().__init__(inst, **kw)
        self.bb_nodecap = bb_nodecap
        self.bb_depthcap = bb_depthcap
        self.ga_budget = ga_budget
        self.ga_pop = ga_pop
        self.ga_gens = ga_gens
        self.use_bb = use_bb
        self.use_ga = use_ga
        self.bb_yes = bb_yes
        self.bb_lp = 0
        self.cert_lp_total = 0
        self.pin_lp_total = 0
        self.ga_stats = []
        self.stats.update(bb_yes=0, bb_no=0, bb_unknown=0,
                          ga_yes=0, ga_no=0, chd_fallback=0)

    def _ensure_lb_proof(self, value):
        p = super()._ensure_lb_proof(value)
        if p is not None:
            return p
        best = None
        for h, src in self.proofs.items():
            if h >= value - 1 and (best is None or h < best[0]):
                best = (h, src)
        if best is not None:
            return self._record_proof(
                SubsumptionProof(self.inst, value - 1, best[1]))
        return None

    def _probe(self, h):
        if self.use_bb:
            r = lp_branch_decide(self.inst, h,
                                 nodecap=self.bb_nodecap,
                                 depthcap=self.bb_depthcap)
            self.bb_lp += r['lp_solves']
            self.cert_lp_total += r.get('cert_lp', 0)
            if r['verdict'] is False:
                self.stats['bb_no'] += 1
                self._record_proof(r['proof'])
                return False, r['proof']
            if r['verdict'] is True and self.bb_yes:
                s, m = r['schedule'], r['machine']
                cmax = max(s[i] + self.inst['p'][i]
                           for i in range(self.inst['n']))
                if check_schedule(self.inst, h, s, m):
                    self.stats['bb_yes'] += 1
                    return True, (s, m, cmax)
            if r['verdict'] is True:
                self.stats['bb_yes_ignored'] = self.stats.get('bb_yes_ignored', 0) + 1
            else:
                self.stats['bb_unknown'] += 1
        if self.use_ga:
            got, st = ga_schedule(self.inst, h, pop=self.ga_pop,
                                  gens=self.ga_gens,
                                  budget=self.ga_budget)
            self.ga_stats.append(st)
            if got is not None:
                s, m = got
                cmax = max(s[i] + self.inst['p'][i]
                           for i in range(self.inst['n']))
                self.stats['ga_yes'] += 1
                return True, (s, m, cmax)
            self.stats['ga_no'] += 1
        self.stats['chd_fallback'] += 1
        v, st, rdf = self._decide(h)
        self.queries += 1
        self._absorb(st)
        self._record(h, v, st)
        return v, rdf

    def optimize(self):
        lb, ub, sched, mach = self.initial_bounds()
        if ub is None:
            return self._result()
        self.lb, self.opt = lb, ub
        self.schedule, self.machine = sched, mach
        self.lb0, self.ub0 = lb, ub
        self.pin_lp_total = getattr(self, 'pin_lp', 0)

        if self.lb == self.opt:
            self._final_proof()
            return self._result()

        while self.lb < self.opt and self.queries < self.max_queries:
            if self.opt - self.lb <= self.scan_cap:
                h = self.lb
                self.stats['scan_q'] += 1
            else:
                h = (self.lb + self.opt) // 2
                self.stats['bin_q'] += 1
            v, payload = self._probe(h)
            if v is True:
                if isinstance(payload, tuple):
                    s, m, cmax = payload
                else:
                    rdf = payload
                    s, m = rdf.schedule, rdf.machine
                    cmax = max(s[i] + self.inst['p'][i]
                               for i in range(self.inst['n']))
                if cmax < self.opt and check_schedule(self.inst, cmax, s, m):
                    self.schedule = list(s)
                    self.machine = list(m)
                    self.opt = cmax
            elif v is False:
                self.lb = max(self.lb, h + 1)
                if isinstance(payload, Proof):
                    self._record_proof(payload)
                    self.lb_proof = payload
                else:
                    self.no_states[h] = payload
                    self.lb_proof = payload
            else:
                self.unknown += 1
                self._recover_unknown(h)

        if self.lb == self.opt:
            self._final_proof()
        return self._result()


def run(cls, inst, known, name, idx, **kw):
    t0 = time.time()
    co = cls(inst, **kw)
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
                   and r['audit'] and r['proof']
                   and r['cert_h'] == known - 1)
    return r
