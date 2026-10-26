"""v9.1 CIFER: Certified Invariant Frontier with Evolutionary Repair.

CIFER extends v9.0 ICF-PACT in three directions suggested by the round's
inspiration words:

  * backtracking: the single open leaf becomes a live frontier.  A DFS
    stack expands a box, probes it, and on UNKNOWN splits it into two
    disjoint sub-boxes.  When a subtree is closed (or the incumbent U
    drops below its local lower bound) the search backtracks to the
    pending sibling.  Every frontier state is itself a partial
    certificate.
  * evolutionary algorithm: every probe first tries a small memetic
    genetic search for a verified schedule at the requested horizon.
    A success is a YES witness with no LP solve.  The same search also
    repairs the incumbent upper bound between exact probes.
  * supervised learning: a ridge regression trained offline predicts the
    largest NO horizon (OPT-1) from cheap instance features.  The
    prediction only chooses the next probe height; it is never trusted.

Trusted objects are unchanged: BranchProof / Farkas / energy NO proofs,
checked schedules, and the frontier partition.  The learned predictor and
the EA can only change the order in which sound evidence is sought.

The main invariant of a frontier state is

    every open leaf f has pi_f : NO(L_f - 1 | F_f),
    every closed leaf c has pi_c : NO(h_c | F_c) with h_c >= U - 1,
    s is feasible and Cmax(s) = U,
    the leaves partition the root box at the target horizon,
    L = min(U, min_f L_f) <= U.

Thus a stopped state is a certified bracket [L,U]; if L=U it is an
optimality certificate.
"""
from __future__ import annotations

import sys
import time
import math
import random

sys.path[:0] = ['exp/v9cf', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof, bound_lb
from sage import BranchProof, _domain, ga_schedule
from sdecc import SDLP
from cert import verify, integer_certificate
from rdf import check_schedule
from po import heads_tails
from pact import PACT, pact_decide, _integral_schedule
from icf import (PartialCertificate, ICFCertificate, cmax,
                 corpora, _proof_forbid)
from scale import _machine_subsets


# --------------------------------------------------------------- small utils
def _elig_aware(inst):
    return any(len(set(inst['elig'][i])) < inst['m']
               for i in range(inst['n']))


def _allowed_times(inst, h, i, F):
    lo, hi = _domain(inst, h, i)
    return [t for t in range(lo, hi + 1) if (i, t) not in F]


def _box_hull(inst, h, F):
    """Interval hull of the allowed starts of every job at horizon h.

    A NO proof for the hull is a valid NO proof for the (possibly
    non-interval) box F.  Returns None if some job has empty domain.
    """
    n = inst['n']
    lo, hi = [], []
    for i in range(n):
        times = _allowed_times(inst, h, i, F)
        if not times:
            return None
        lo.append(min(times))
        hi.append(max(times))
    return lo, hi


def _verify_box_cert(inst, h, lo, hi, cert):
    if cert is None:
        return False
    n, p = inst['n'], inst['p']
    if cert.get('kind') == 'window':
        i = cert.get('job', -1)
        return (0 <= i < n and lo[i] > hi[i]
                and cert.get('est') == lo[i]
                and cert.get('lst') == hi[i])
    if cert.get('kind') == 'energy':
        M = set(cert.get('M', ()))
        a, b = cert.get('a'), cert.get('b')
        if not M or a is None or b is None or a >= b:
            return False
        js = [i for i in range(n) if set(inst['elig'][i]) <= M]
        if js != list(cert.get('jobs', ())):
            return False
        demand = 0
        for i in js:
            demand += max(0, p[i] - max(0, a - lo[i])
                          - max(0, hi[i] + p[i] - b))
        return (demand == cert.get('demand')
                and demand > len(M) * (b - a))
    return False


def _box_energy_cert(inst, h, lo, hi, max_subsets=32,
                     max_intervals=6000):
    """Sound energy/window NO certificate for the interval box [lo,hi]."""
    n, p = inst['n'], inst['p']
    for i in range(n):
        if lo[i] > hi[i]:
            return dict(kind='window', job=i, est=lo[i], lst=hi[i])
    pts = sorted(set(lo + [hi[i] + p[i] for i in range(n)]))
    pairs = [(0, h)] if 0 < h else []
    for ai, x in enumerate(pts):
        for y in pts[ai + 1:]:
            if (x, y) != (0, h):
                pairs.append((x, y))
            if len(pairs) >= max_intervals:
                break
        if len(pairs) >= max_intervals:
            break
    for M in _machine_subsets(inst, max_subsets):
        js = [i for i in range(n) if set(inst['elig'][i]) <= M]
        if not js:
            continue
        cap = len(M)
        for x, y in pairs:
            if y <= x:
                continue
            demand = 0
            for i in js:
                demand += max(0, p[i] - max(0, x - lo[i])
                              - max(0, hi[i] + p[i] - y))
            if demand > cap * (y - x):
                return dict(kind='energy', M=sorted(M), a=x, b=y,
                            jobs=js, demand=demand, cap=cap * (y - x))
    return None


class BoxEnergyProof(Proof):
    """A NO proof for the interval hull of a box at horizon h."""

    kind = 'box-energy'

    def __init__(self, inst, h, lo, hi, cert):
        super().__init__(inst, h)
        self.lo = tuple(int(x) for x in lo)
        self.hi = tuple(int(x) for x in hi)
        self.cert = cert
        self.kind = 'box-' + str(cert.get('kind', 'energy')) \
            if cert else 'box-energy'
        self.forbid0 = frozenset()

    def audit_rdf(self):
        try:
            return _verify_box_cert(self.inst, self.h, self.lo, self.hi,
                                    self.cert)
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


class EmptyBoxProof(Proof):
    """A leaf that has no allowed start vector at the target horizon."""

    kind = 'empty-box'

    def __init__(self, inst, h, F):
        super().__init__(inst, h)
        self.F = frozenset(F)
        self.forbid0 = frozenset()

    def audit_rdf(self):
        try:
            return _box_hull(self.inst, self.h, self.F) is None
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


# --------------------------------------------------------------- EA primal
def _sgs_forbid(inst, rank, F, h):
    """Serial SGS with forbidden start pairs.  Returns (s,m,cmax) or None."""
    n, m, p = inst['n'], inst['m'], inst['p']
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
        av.sort(key=lambda i: (rank[i], i))
        i = av[0]
        base = predfin[i]
        best = None
        for k in inst['elig'][i]:
            t = base
            limit = h - p[i]
            while t <= limit:
                if (i, t) in F:
                    t += 1
                    continue
                end = t + p[i]
                if all(end <= a or t >= b for a, b in busy[k]):
                    cand = (t, end, k)
                    if best is None or cand < best:
                        best = cand
                    break
                # jump to the end of the first blocking interval
                jump = None
                for a, b in busy[k]:
                    if not (end <= a or t >= b):
                        jump = b if jump is None else min(jump, b)
                t = (jump if jump is not None else t) + 1
        if best is None:
            return None
        tt, ft, k = best
        starts[i] = tt
        machs[i] = k
        done[i] = True
        busy[k].append((tt, ft))
        busy[k].sort()
        for j in inst['succ'][i]:
            predfin[j] = max(predfin[j], ft)
            rem[j] -= 1
    c = max(starts[i] + p[i] for i in range(n))
    if c <= h and check_schedule(inst, c, starts, machs):
        return starts, machs, c
    return None


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


def ea_probe(inst, h, F=frozenset(), pop=14, gens=8, budget=240,
             seed=0, incumbent=None):
    """Memetic search for a verified schedule of makespan <= h.

    The decoder respects F, so a success is also a valid YES witness for
    the leaf box.  Returns ((s,m), stats) or (None, stats).
    """
    t0 = time.time()
    rng = random.Random(20261026 + seed * 100003)
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    latest = [h - q[i] - inst['p'][i] for i in range(n)]
    seeds = []
    for key in (lambda i: est[i], lambda i: latest[i],
                lambda i: -q[i],
                lambda i: est[i] - 0.5 * q[i]):
        seeds.append(sorted(range(n), key=lambda i: (key(i), i)))
    if incumbent is not None:
        seeds.append(sorted(range(n),
                            key=lambda i: (incumbent[i], i)))
    P = list(seeds)
    while len(P) < pop:
        a = list(range(n))
        rng.shuffle(a)
        P.append(a)
    cache = {}
    used = [0]

    def score(p):
        key = tuple(p)
        if key not in cache:
            g = _sgs_forbid(inst, {p[k]: k + 1e-7 * ((p[k] * 7919) % 101)
                                   for k in range(n)}, F, h)
            if g is None:
                cache[key] = ((10 ** 9, 10 ** 9), None)
            else:
                s, m, c = g
                cache[key] = ((c, sum(s[i] + inst['p'][i]
                                      for i in range(n))), (s, m))
            used[0] += 1
        return cache[key][0]

    for p in P:
        score(p)
    bestp = min(P, key=score)
    bestf = score(bestp)
    gens_used = 0
    for _ in range(gens):
        if bestf[0] <= h or used[0] >= budget:
            break
        gens_used += 1
        P.sort(key=score)
        new = P[:3]
        while len(new) < pop and used[0] < budget:
            a = rng.choice(P[:max(6, pop // 2)])
            b = rng.choice(P[:max(6, pop // 2)])
            child = _ox(a, b, rng)
            if rng.random() < 0.7:
                child = _mutate(child, rng)
            new.append(child)
            score(child)
        P = new
        cp = min(P, key=score)
        if score(cp) < bestf:
            bestp, bestf = cp, score(cp)
    got = cache.get(tuple(bestp))
    st = dict(evals=used[0], gens=gens_used, best=bestf[0],
              t=round(time.time() - t0, 5))
    if got is None or got[1] is None:
        return None, st
    s, m = got[1]
    c = max(s[i] + inst['p'][i] for i in range(n))
    if c <= h and check_schedule(inst, c, s, m):
        return (s, m), st
    return None, st


def ea_repair(inst, U, sched, mach, L=0, budget=1200, pop=40,
              gens=60, seed=0):
    """Memetic repair of the incumbent upper bound.

    Each round asks for a verified schedule with makespan <= U-1.  The
    returned schedule is checked independently before it is accepted.
    """
    t0 = time.time()
    evals = 0
    rounds = 0
    drops = 0
    while evals < budget and U > L:
        got, st = ga_schedule(inst, U - 1, pop=pop, gens=gens,
                              budget=min(600, budget - evals),
                              seed=seed + rounds)
        evals += st.get('evals', 0)
        rounds += 1
        if got is None:
            break
        s, m = got
        c = cmax(inst, s)
        if L <= c < U and check_schedule(inst, c, s, m):
            U, sched, mach = c, list(s), list(m)
            drops += 1
        else:
            break
    return U, sched, mach, dict(evals=evals, rounds=rounds,
                                drops=drops,
                                t=round(time.time() - t0, 4))


# --------------------------------------------------------------- branch split
def choose_split(inst, h, F, z_hint=None):
    """Choose (i, mid, lp_stats) for a fractional box, or None.

    This mirrors the PACT branching score: the job with the largest
    fractional mass, split at the mass median.  It is a search heuristic,
    not a proof rule.
    """
    n = inst['n']
    elig = _elig_aware(inst)
    est, q = heads_tails(inst, 0, [0] * n)
    lp = SDLP(inst, h, est, q, use_dom=True, elig_aware=elig,
              forbid=F)
    stats = dict(lp_solves=0, status=None, split_job=None, split_mid=None)
    if lp.N <= 0:
        stats['status'] = 'empty'
        return None, stats
    res = lp.solve([(0, 1)] * lp.N)
    stats['lp_solves'] = 1
    stats['status'] = res.status
    if res.status != 0:
        return None, stats
    z = res.x
    cand = []
    for i in range(n):
        times = sorted({key[-1] for c, key in enumerate(lp.cols)
                        if key[0] == i})
        if len(times) <= 1:
            continue
        dist = []
        for tt in times:
            v = sum(z[c] for c, key in enumerate(lp.cols)
                    if key[0] == i and key[-1] == tt)
            dist.append((tt, v))
        frac = sum(v for _, v in dist if 1e-7 < v < 1 - 1e-7)
        if frac <= 1e-7:
            continue
        mass = sum(v for _, v in dist)
        cand.append((frac, mass, i, dist))
    if cand:
        cand.sort(key=lambda x: (-x[0], -x[1], x[2]))
        _, _, i, dist = cand[0]
        total = sum(v for _, v in dist)
        acc = 0.0
        mid = dist[0][0]
        for tt, v in dist:
            acc += v
            if acc >= 0.5 * total:
                mid = tt
                break
    else:
        # integral LP but no schedule was extracted: split a wide job.
        wide = []
        for i in range(n):
            times = sorted({key[-1] for c, key in enumerate(lp.cols)
                            if key[0] == i})
            if len(times) > 1:
                wide.append((len(times), i, times))
        if not wide:
            return None, stats
        wide.sort(reverse=True)
        _, i, times = wide[0]
        mid = times[(len(times) - 1) // 2]
    allowed = _allowed_times(inst, h, i, F)
    lo_t = [t for t in allowed if t > mid]
    hi_t = [t for t in allowed if t <= mid]
    if not lo_t or not hi_t:
        mid = allowed[len(allowed) // 2 - 1] if len(allowed) > 1 else \
            allowed[0]
        lo_t = [t for t in allowed if t > mid]
        hi_t = [t for t in allowed if t <= mid]
    if not lo_t or not hi_t:
        return None, stats
    stats['split_job'] = i
    stats['split_mid'] = mid
    return (i, mid), stats


def split_box(inst, h, F, i, mid):
    allowed = _allowed_times(inst, h, i, F)
    lo_t = [t for t in allowed if t > mid]
    hi_t = [t for t in allowed if t <= mid]
    if not lo_t or not hi_t:
        return None
    F_left = frozenset(set(F) | {(i, t) for t in lo_t})
    F_right = frozenset(set(F) | {(i, t) for t in hi_t})
    return F_left, F_right, lo_t, hi_t


# --------------------------------------------------------------- frontier
class Node:
    __slots__ = ('F', 'Lf', 'proof', 'status', 'split', 'left', 'right',
                 'depth', 'h_close', 'parent')

    def __init__(self, F, Lf, proof, depth=0, parent=None):
        self.F = frozenset(F)
        self.Lf = int(Lf)
        self.proof = proof
        self.status = 'open'
        self.split = None
        self.left = None
        self.right = None
        self.depth = int(depth)
        self.h_close = None
        self.parent = parent


class CiferState:
    """A live frontier plus its invariant checker.

    It is both the running state and the partial/final certificate.
    """

    kind = 'cifer-frontier'

    def __init__(self, inst, root, U, schedule, machine, L=None):
        self.inst = inst
        self.root = root
        self.U = int(U)
        self.schedule = (list(schedule)
                         if schedule is not None else None)
        self.machine = (list(machine)
                        if machine is not None else None)
        self.L = int(L) if L is not None else None

    def leaves(self):
        out = []
        stack = [self.root]
        while stack:
            x = stack.pop()
            if x.status == 'internal':
                stack.append(x.right)
                stack.append(x.left)
            else:
                out.append(x)
        return out

    def compute_L(self):
        L = self.U
        for f in self.leaves():
            if f.status in ('open', 'hole'):
                L = min(L, f.Lf)
        return L

    def _target_allowed(self, F, i, h):
        lo, hi = _domain(self.inst, h, i)
        return [t for t in range(lo, hi + 1) if (i, t) not in F]

    def _check_leaf(self, f, target, require_final):
        if f.status == 'closed':
            if f.proof is None:
                return False
            if f.proof.h < target:
                return False
            if not f.proof.audit_rdf():
                return False
            if not set(_proof_forbid(f.proof)) <= set(f.F):
                return False
            return True
        if f.status in ('open', 'hole'):
            if require_final:
                return False
            if f.proof is None or f.proof.h != f.Lf - 1:
                return False
            if not f.proof.audit_rdf():
                return False
            if not set(_proof_forbid(f.proof)) <= set(f.F):
                return False
            return f.Lf <= self.U
        return False

    def _check_tree(self, x, target, require_final):
        if x.status == 'internal':
            if x.left is None or x.right is None:
                return False
            if not self._check_tree(x.left, target, require_final):
                return False
            return self._check_tree(x.right, target, require_final)
        return self._check_leaf(x, target, require_final)

    def _check_partition(self, x, h):
        """Every split partitions the parent box on the split job at h."""
        if x.status != 'internal':
            return True
        i, mid, _ = x.split
        parent_allowed = set(self._target_allowed(x.F, i, h))
        left_allowed = set(self._target_allowed(x.left.F, i, h))
        right_allowed = set(self._target_allowed(x.right.F, i, h))
        if left_allowed & right_allowed:
            return False
        if left_allowed | right_allowed != parent_allowed:
            return False
        if not set(x.F) <= set(x.left.F):
            return False
        if not set(x.F) <= set(x.right.F):
            return False
        return (self._check_partition(x.left, h)
                and self._check_partition(x.right, h))

    def _sched_ok(self):
        if self.schedule is None or self.machine is None:
            return False
        c = cmax(self.inst, self.schedule)
        return (c == self.U
                and bool(check_schedule(self.inst, c, self.schedule,
                                        self.machine)))

    def audit_rdf(self, require_final=False):
        try:
            if not self._sched_ok():
                return False
            target = max(0, self.U - 1)
            if not self._check_tree(self.root, target, require_final):
                return False
            if not self._check_partition(self.root, target):
                return False
            L = self.compute_L()
            if self.L is not None and L != self.L:
                return False
            if L > self.U:
                return False
            if require_final and L != self.U:
                return False
            return True
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf(require_final=True)


# --------------------------------------------------------------- policies
def choose_h(L, U, pred, policy, first):
    if U <= L:
        return L
    if policy == 'lower-first':
        return L if first else (L + U) // 2
    if policy == 'upper-first':
        return U - 1
    if policy == 'binary':
        return (L + U) // 2
    if policy == 'learned':
        if pred is None:
            return (L + U) // 2
        return max(L, min(U - 1, int(round(pred))))
    if policy == 'pred-first':
        if first and pred is not None:
            return max(L, min(U - 1, int(round(pred))))
        return (L + U) // 2
    if policy == 'hybrid':
        if first:
            return L
        if pred is not None:
            h = int(round(pred))
            if L < h < U:
                return h
        return (L + U) // 2
    if policy == 'learned-binary':
        if pred is not None:
            h = int(round(pred))
            if L < h < U:
                return h
        return L if first else (L + U) // 2
    raise ValueError('unknown policy %r' % (policy,))


# --------------------------------------------------------------- CIFER run
def _initial_proof(inst, co, L0, stats):
    p = co._ensure_lb_proof(L0)
    if p is not None and p.h == L0 - 1 and p.audit_rdf():
        return p
    r = pact_decide(inst, L0 - 1, depthcap=None, nodecap=None)
    stats['prep_lp'] += r.get('lp_solves', 0)
    stats['prep_cert_lp'] += r.get('cert_lp', 0)
    if r['verdict'] is False and r['proof'] is not None:
        return r['proof']
    return None


def run_cifer(inst, known, name, idx, policy='hybrid', pred=None,
              nodecap=1, depthcap=None, max_probes=128, max_splits=64,
              max_depth=10, ea_mode='probe', ea_pop=12, ea_gens=6,
              ea_budget=180, ea_init_budget=0, ea_push_budget=0,
              audit=True, L0_override=None, U0_override=None, seed=0):
    """Run CIFER on one instance and return a benchmark row."""
    t0 = time.time()
    stats = dict(probes=0, lp=0, cert_lp=0, nodes=0, ea_evals=0,
                 ea_success=0, static_no=0, static_lift=0,
                 splits=0, closed=0, holes=0, max_depth=0,
                 prep_lp=0, prep_cert_lp=0, audit_ok=0, audit_fail=0,
                 final_fallback=0, unsat_split=0, unknown=0)
    co = PACT(inst, pact_mode='complete', use_ga=False)
    lb, ub, sched, mach = co.initial_bounds()
    if ub is None or sched is None:
        return dict(name=name, idx=idx, known=known, policy=policy,
                    ok=False, error='no-initial-ub', t=0.0, **stats)
    init_lp = getattr(co, 'pin_lp', 0)
    L0 = int(lb if L0_override is None else L0_override)
    U = int(cmax(inst, sched) if U0_override is None else U0_override)
    if U0_override is not None:
        # Need a schedule with exactly this upper bound.  The initial one
        # may be shorter; a shorter schedule is a better incumbent.
        c0 = cmax(inst, sched)
        if c0 < U:
            U = c0
    sched = list(sched)
    mach = list(mach)
    if not (0 <= L0 <= U):
        return dict(name=name, idx=idx, known=known, policy=policy,
                    ok=False, error='bad-bracket', t=0.0, **stats)
    init_U = U
    ea_init = dict(evals=0, rounds=0, drops=0, t=0.0)
    ea_push = dict(evals=0, success=False, cmax=None, t=0.0)
    if ea_push_budget > 0 and L0 < U:
        t_push = time.time()
        got, st = ga_schedule(inst, L0, pop=40, gens=60,
                              budget=ea_push_budget, seed=seed)
        ea_push = dict(evals=st.get('evals', 0),
                       success=False, cmax=None,
                       t=round(time.time() - t_push, 4))
        stats['ea_evals'] += ea_push['evals']
        if got is not None:
            s2, m2 = got
            c2 = cmax(inst, s2)
            ea_push['cmax'] = c2
            if c2 == L0 and check_schedule(inst, c2, s2, m2):
                U, sched, mach = c2, list(s2), list(m2)
                ea_push['success'] = True
    if ea_init_budget > 0 and L0 < U:
        U, sched, mach, ea_init = ea_repair(
            inst, U, sched, mach, L=L0, budget=ea_init_budget,
            seed=seed)
        stats['ea_evals'] += ea_init.get('evals', 0)
    proof0 = _initial_proof(inst, co, L0, stats)
    if proof0 is None:
        return dict(name=name, idx=idx, known=known, policy=policy,
                    ok=False, error='no-initial-proof', t=0.0, **stats)
    root = Node(frozenset(), L0, proof0)
    state = CiferState(inst, root, U, sched, mach, L=compute_L(root, U))
    stack = [root]
    steps = []
    lb0, ub0 = L0, U

    def sync():
        state.U = U
        state.schedule = sched
        state.machine = mach
        state.L = compute_L(root, U)

    def close_node(x):
        x.status = 'closed'
        x.h_close = x.Lf - 1
        stats['closed'] += 1

    def close_empty(x, target):
        if x.status in ('open', 'closed'):
            x.proof = EmptyBoxProof(inst, target, x.F)
            x.status = 'closed'
            x.h_close = target
            stats['closed'] += 1
            return True
        return False

    def sweep():
        """Close frontier leaves whose local bound already implies NO(U-1)."""
        target = max(0, U - 1)
        for x in state.leaves():
            if x.status in ('open', 'hole') and x.Lf >= U:
                x.status = 'closed'
                x.h_close = x.Lf - 1
                stats['closed'] += 1
            elif x.status in ('open', 'hole'):
                if _box_hull(inst, target, x.F) is None:
                    close_empty(x, target)
        # remove closed nodes from the DFS stack
        stack[:] = [x for x in stack if x.status == 'open']

    def audit_state():
        if not audit:
            return True
        sync()
        ok = state.audit_rdf(require_final=False)
        if ok:
            stats['audit_ok'] += 1
        else:
            stats['audit_fail'] += 1
        return ok

    def apply_no(x, h, proof):
        x.Lf = h + 1
        x.proof = proof
        if x.Lf >= U:
            close_node(x)
            return True
        return False

    def apply_yes(x, s2, m2):
        nonlocal U, sched, mach
        c2 = cmax(inst, s2)
        if c2 <= U and check_schedule(inst, c2, s2, m2):
            if c2 < U:
                U = c2
                sched = list(s2)
                mach = list(m2)
                sweep()
            return True
        return False

    def static_lift(x, start, max_steps=4):
        h = start
        proof = None
        k = 0
        while h < U and k < max_steps:
            hull = _box_hull(inst, h, x.F)
            if hull is None:
                return h, proof, k
            lo, hi = hull
            cert = _box_energy_cert(inst, h, lo, hi)
            if cert is None:
                break
            proof = BoxEnergyProof(inst, h, lo, hi, cert)
            h += 1
            k += 1
        return h, proof, k

    def probe_node(x):
        nonlocal U, sched, mach
        first = True
        escalated = 0
        while x.status == 'open' and x.Lf < U:
            h = choose_h(x.Lf, U, pred, policy, first)
            first = False
            # Empty at this probe horizon: NO(h) is trivial.
            hull = _box_hull(inst, h, x.F)
            if hull is None:
                p = EmptyBoxProof(inst, h, x.F)
                steps.append(dict(kind='empty-no', h=h, L0=x.Lf,
                                  U0=U))
                if apply_no(x, h, p):
                    return
                continue
            lo, hi = hull
            cert = _box_energy_cert(inst, h, lo, hi)
            if cert is not None:
                stats['static_no'] += 1
                p = BoxEnergyProof(inst, h, lo, hi, cert)
                # Try to lift several horizons with the same cheap test.
                h2, p2, k = static_lift(x, h + 1)
                if p2 is not None:
                    p = p2
                    h = h2 - 1
                    stats['static_lift'] += k
                steps.append(dict(kind='static-no', h=h, L0=x.Lf,
                                  U0=U))
                if apply_no(x, h, p):
                    return
                continue
            # Cheap primal witness: EA at h.
            if ea_mode in ('probe', 'both'):
                got, ast = ea_probe(inst, h, x.F, pop=ea_pop,
                                    gens=ea_gens, budget=ea_budget,
                                    seed=seed + stats['probes'],
                                    incumbent=sched)
                stats['ea_evals'] += ast['evals']
                if got is not None:
                    stats['ea_success'] += 1
                    s2, m2 = got
                    steps.append(dict(kind='ea-yes', h=h, L0=x.Lf,
                                      U0=U, cmax=cmax(inst, s2)))
                    apply_yes(x, s2, m2)
                    if x.status == 'closed' or U <= x.Lf:
                        close_node(x)
                        return
                    continue
            # Exact fixed-h decision at this leaf.
            r = pact_decide(inst, h, forbid0=x.F,
                            depthcap=depthcap, nodecap=nodecap)
            stats['probes'] += 1
            stats['lp'] += r.get('lp_solves', 0)
            stats['cert_lp'] += r.get('cert_lp', 0)
            stats['nodes'] += r.get('nodes', 0)
            if r['verdict'] is False:
                proof = r['proof']
                if proof is None or proof.h != h or not proof.audit_rdf():
                    stats['unknown'] += 1
                    x.status = 'hole'
                    stats['holes'] += 1
                    return
                steps.append(dict(kind='no', h=h, L0=x.Lf, U0=U,
                                  proof=getattr(proof, 'kind', None)))
                if apply_no(x, h, proof):
                    return
                continue
            if r['verdict'] is True:
                s2, m2 = r['schedule'], r['machine']
                steps.append(dict(kind='yes', h=h, L0=x.Lf, U0=U,
                                  cmax=cmax(inst, s2)))
                apply_yes(x, s2, m2)
                if x.status == 'closed' or U <= x.Lf:
                    close_node(x)
                    return
                continue
            # UNKNOWN: split the box at the *target* horizon U-1 so that
            # the partition is valid for the final frontier proof, then
            # backtrack through the children.
            stats['unknown'] += 1
            target = max(0, U - 1)
            if _box_hull(inst, target, x.F) is None:
                close_empty(x, target)
                return
            if stats['splits'] >= max_splits or x.depth >= max_depth:
                x.status = 'hole'
                stats['holes'] += 1
                return
            split, st = choose_split(inst, target, x.F)
            stats['lp'] += st.get('lp_solves', 0)
            if split is None and st.get('status') == 2:
                # The target LP is infeasible: close with a Farkas proof.
                cert = integer_certificate(inst, target, forbid=x.F)
                if cert is not None and verify(inst, target, cert,
                                               forbid=x.F):
                    from icf import CertLeafProof
                    p = CertLeafProof(inst, target, x.F, cert)
                    steps.append(dict(kind='target-no', h=target,
                                      L0=x.Lf, U0=U))
                    if apply_no(x, target, p):
                        return
                    continue
            if split is None:
                # Budget escalation: one deeper exact attempt at h.
                if escalated < 1:
                    escalated += 1
                    r2 = pact_decide(inst, h, forbid0=x.F,
                                     depthcap=depthcap,
                                     nodecap=(32 if nodecap is not None
                                              else None))
                    stats['probes'] += 1
                    stats['lp'] += r2.get('lp_solves', 0)
                    stats['cert_lp'] += r2.get('cert_lp', 0)
                    stats['nodes'] += r2.get('nodes', 0)
                    if r2['verdict'] is False and r2['proof'] is not None:
                        steps.append(dict(kind='no-escalated', h=h,
                                          L0=x.Lf, U0=U))
                        if apply_no(x, h, r2['proof']):
                            return
                        continue
                    if r2['verdict'] is True:
                        steps.append(dict(kind='yes-escalated', h=h,
                                          L0=x.Lf, U0=U,
                                          cmax=cmax(inst, r2['schedule'])))
                        apply_yes(x, r2['schedule'], r2['machine'])
                        if x.status == 'closed' or U <= x.Lf:
                            close_node(x)
                            return
                        continue
                stats['unsat_split'] += 1
                x.status = 'hole'
                stats['holes'] += 1
                return
            i, mid = split
            parts = split_box(inst, target, x.F, i, mid)
            if parts is None:
                stats['unsat_split'] += 1
                x.status = 'hole'
                stats['holes'] += 1
                return
            F_left, F_right, lo_t, hi_t = parts
            left = Node(F_left, x.Lf, x.proof, x.depth + 1, x)
            right = Node(F_right, x.Lf, x.proof, x.depth + 1, x)
            x.status = 'internal'
            x.split = (i, mid, target)
            x.left, x.right = left, right
            stats['splits'] += 1
            stats['max_depth'] = max(stats['max_depth'], x.depth + 1)
            # Explore the side consistent with the incumbent first.
            first_child, second_child = left, right
            if sched is not None and sched[i] > mid:
                first_child, second_child = right, left
            stack.append(second_child)
            stack.append(first_child)
            return

    # Initial state audit.
    audit_state()
    while stack:
        sync()
        if state.L >= U:
            break
        x = stack.pop()
        if x.status != 'open':
            continue
        if x.Lf >= U:
            close_node(x)
            continue
        if _box_hull(inst, max(0, U - 1), x.F) is None:
            close_empty(x, max(0, U - 1))
            continue
        probe_node(x)
        sync()
        sweep()
        audit_state()

    sync()
    L = state.L
    if L == U:
        for f in state.leaves():
            if f.status in ('open', 'hole') and f.Lf >= U:
                f.status = 'closed'
                f.h_close = f.Lf - 1
                stats['closed'] += 1
        sync()
        L = state.L
    final_ok = False
    final_kind = None
    if L == U:
        final_ok = bool(state.audit_rdf(require_final=True))
        final_kind = 'frontier' if final_ok else None
        if not final_ok:
            # Safe fallback: a complete single-horizon NO proof.
            stats['final_fallback'] += 1
            r = pact_decide(inst, U - 1, depthcap=None, nodecap=None)
            stats['lp'] += r.get('lp_solves', 0)
            stats['cert_lp'] += r.get('cert_lp', 0)
            if r['verdict'] is False and r['proof'] is not None:
                try:
                    icf = ICFCertificate(inst, U, sched, mach, r['proof'])
                    final_ok = bool(icf.audit_rdf())
                    final_kind = 'icf-fallback' if final_ok else None
                except Exception:
                    final_ok = False
    partial_ok = bool(state.audit_rdf(require_final=False))
    dt = time.time() - t0
    leaves = state.leaves()
    return dict(
        name=name, idx=idx, known=known, policy=policy,
        L=L, U=U, lb0=lb0, ub0=ub0, init_U=init_U,
        ea_init=ea_init, ea_push=ea_push, gap=U - L,
        certified=bool(L == U and final_ok),
        final_kind=final_kind, final_audit=final_ok,
        partial_audit=partial_ok,
        probes=stats['probes'], lp=stats['lp'] + stats['prep_lp'],
        cert_lp=stats['cert_lp'] + stats['prep_cert_lp'],
        nodes=stats['nodes'], init_lp=init_lp,
        prep_lp=stats['prep_lp'],
        ea_evals=stats['ea_evals'], ea_success=stats['ea_success'],
        static_no=stats['static_no'], static_lift=stats['static_lift'],
        splits=stats['splits'], closed=stats['closed'],
        holes=stats['holes'], max_depth=stats['max_depth'],
        leaves=len(leaves),
        closed_leaves=sum(1 for f in leaves if f.status == 'closed'),
        audit_ok=stats['audit_ok'], audit_fail=stats['audit_fail'],
        unknown=stats['unknown'],
        steps=steps, t=round(dt, 4),
        ok=bool(L == U and U == known and final_ok
                and partial_ok and stats['audit_fail'] == 0),
    )


def compute_L(root, U):
    L = U
    stack = [root]
    while stack:
        x = stack.pop()
        if x.status == 'internal':
            stack.append(x.right)
            stack.append(x.left)
        elif x.status in ('open', 'hole'):
            L = min(L, x.Lf)
    return L
