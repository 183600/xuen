"""v8.9 RIG-SAGE: randomized rounding + iterated greedy on top of SAGE-ALC.

SAGE's upper side still spends LP-BRANCH nodes on probes whose root LP is
fractional but whose horizon is feasible.  RIG-SAGE inserts a randomized
construction before the proof search:

  * RR-UB: solve the fixed-h SD LP once, sample a start time for every job
    from the fractional LP distribution, and decode the sampled priorities
    with a serial SGS.  Any schedule with Cmax <= h is accepted only after
    check_schedule.
  * IG-UB: if LP-BRANCH later returns UNKNOWN, improve the best RR
    permutation by a destroy-and-reinsert iterated greedy.  Again only a
    checked schedule is accepted.
  * LP-BRANCH and STAB stay exactly as in SAGE; the randomized layer only
    chooses an upper-bound witness, never a verdict or a lower-bound proof.

The random choices are a Las Vegas search: a wrong sample simply fails the
check and the next sample or the deterministic proof engine takes over.
"""
import sys
import time
import random
import math

sys.path[:0] = ['exp/v8m', 'exp/v8i', 'exp/v8h', 'exp/v8f', 'exp/v8e',
                'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from sage import SAGE, _elig_aware, ga_schedule
from sdecc import SDLP
from rdf import check_schedule
from po import heads_tails
from cab import _greedy_rank


def _lp_distribution(inst, h):
    """Return (lp, dist, integral) for the root LP at h.

    dist[i] is a list of (start, machine, mass); the masses of job i sum
    to one.  integral is a full start/machine vector when the root LP is
    already integral.
    """
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    elig = _elig_aware(inst)
    lp = SDLP(inst, h, est, q, use_dom=True, elig_aware=elig)
    if lp.N == 0:
        return lp, None, None
    res = lp.solve()
    if res.status == 2:
        return lp, None, None
    if res.status != 0:
        return lp, None, None
    z = res.x
    dist = [[] for _ in range(n)]
    starts = [None] * n
    machs = [None] * n
    integral = True
    for c, key in enumerate(lp.cols):
        i, t = key[0], key[-1]
        m = key[1] if len(key) > 2 else 0
        if z[c] > 1 - 1e-7:
            if starts[i] is not None:
                integral = False
            starts[i] = t
            machs[i] = m
        elif 1e-7 < z[c]:
            integral = False
        if z[c] > 1e-9:
            dist[i].append((t, m, z[c]))
    if integral and all(x is not None for x in starts):
        if check_schedule(inst, h, starts, machs):
            return lp, dist, (starts, machs)
    return lp, dist, None


def _sample_rank(dist, rng, jitter=0.999):
    rank = {}
    for i, d in enumerate(dist):
        if d:
            total = sum(v for _, _, v in d)
            r = rng.random() * total
            acc = 0.0
            pick = d[-1]
            for t, m, v in d:
                acc += v
                if acc >= r:
                    pick = (t, m, v)
                    break
            rank[i] = pick[0] + rng.random() * jitter
        else:
            rank[i] = rng.random()
    return rank


def _decode(inst, h, rank):
    g = _greedy_rank(inst, rank)
    if g is None:
        return None
    s, m, cmax = g
    if cmax <= h and check_schedule(inst, h, s, m):
        return s, m, cmax
    return None


def rr_ub(inst, h, samples=64, seed=0, jitter=0.999, nseeds=1):
    """Randomized-rounding upper bound at horizon h.

    samples is the number of draws per seed; nseeds independent seeds are
    used.  The LP distribution is solved once and shared.  Returns
    dict(ok, schedule, machine, cmax, best, best_cmax, lp, t).
    best is the best sampled schedule even when it exceeds h; it seeds
    the iterated-greedy repair after an LP-BRANCH UNKNOWN.
    """
    t0 = time.time()
    lp, dist, integral = _lp_distribution(inst, h)
    if dist is None:
        return dict(ok=False, schedule=None, machine=None, cmax=None,
                    best=None, best_cmax=None, samples=0,
                    t=round(time.time() - t0, 5))
    if integral is not None:
        s, m = integral
        cmax = max(s[i] + inst['p'][i] for i in range(inst['n']))
        return dict(ok=cmax <= h, schedule=s, machine=m, cmax=cmax,
                    best=(s, m), best_cmax=cmax, samples=0,
                    t=round(time.time() - t0, 5))
    best = None
    best_cmax = 10 ** 9
    used = 0
    for k in range(nseeds):
        rng = random.Random(0x5A6E + (seed + k) * 1000003)
        for _ in range(samples):
            rank = _sample_rank(dist, rng, jitter)
            g = _greedy_rank(inst, rank)
            used += 1
            if g is None:
                continue
            s, m, cmax = g
            if cmax < best_cmax:
                best_cmax = cmax
                best = (s, m)
            if cmax <= h and check_schedule(inst, h, s, m):
                return dict(ok=True, schedule=s, machine=m, cmax=cmax,
                            best=best, best_cmax=best_cmax, samples=used,
                            t=round(time.time() - t0, 5))
    return dict(ok=False, schedule=None, machine=None, cmax=None,
                best=best, best_cmax=best_cmax, samples=used,
                t=round(time.time() - t0, 5))


def _perm_from_schedule(s, n):
    return sorted(range(n), key=lambda i: (s[i], i))


def _eval_perm(inst, perm):
    rank = {perm[k]: k + 1e-7 * ((perm[k] * 7919) % 101)
            for k in range(len(perm))}
    g = _greedy_rank(inst, rank)
    if g is None:
        return 10 ** 9, None
    return g[2], g


def ig_ub(inst, h, start, budget=3000, seed=0):
    """Destroy-and-reinsert iterated greedy from a start schedule."""
    t0 = time.time()
    rng = random.Random(0xC0FFEE + seed * 100003)
    n = inst['n']
    if start is None:
        return dict(ok=False, schedule=None, machine=None, cmax=None,
                    evals=0, t=round(time.time() - t0, 5))
    best = _perm_from_schedule(start[0], n)
    bf, g = _eval_perm(inst, best)
    used = 1
    if bf <= h and g is not None and check_schedule(inst, h, g[0], g[1]):
        return dict(ok=True, schedule=g[0], machine=g[1], cmax=bf,
                    evals=used, t=round(time.time() - t0, 5))
    while used < budget:
        cand = list(best)
        k = rng.randint(1, min(3, n))
        idx = sorted(rng.sample(range(n), k), reverse=True)
        items = [cand.pop(i) for i in idx]
        for x in items:
            cand.insert(rng.randrange(len(cand) + 1), x)
        f, g2 = _eval_perm(inst, cand)
        used += 1
        if f < bf or (f == bf and rng.random() < 0.3):
            best, bf = cand, f
            if g2 is not None and bf < 10 ** 8:
                g = g2
        if bf <= h and g is not None:
            if check_schedule(inst, h, g[0], g[1]):
                return dict(ok=True, schedule=g[0], machine=g[1],
                            cmax=bf, evals=used,
                            t=round(time.time() - t0, 5))
    return dict(ok=False, schedule=None, machine=None, cmax=bf,
                evals=used, t=round(time.time() - t0, 5))


class RIGSAGE(SAGE):
    """SAGE with a randomized-rounding / iterated-greedy upper side."""

    def __init__(self, inst, rr_samples=20, ig_budget=3000,
                 rr_seed=0, rr_seeds=5, ig_seeds=2,
                 use_rr=True, use_ig=True, cap_first=0, **kw):
        super().__init__(inst, **kw)
        self.rr_samples = rr_samples
        self.rr_seeds = rr_seeds
        self.ig_budget = ig_budget
        self.ig_seeds = ig_seeds
        self.rr_seed = rr_seed
        self.use_rr = use_rr
        self.use_ig = use_ig
        self.cap_first = cap_first
        self.rr_yes = 0
        self.rr_no = 0
        self.ig_yes = 0
        self.ig_no = 0
        self.rr_evals = 0
        self.ig_evals = 0
        self.rr_t = 0.0
        self.ig_t = 0.0
        self.stats.update(rr_yes=0, rr_no=0, ig_yes=0, ig_no=0)

    def _handle_bb(self, h, r):
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
            self.stats['bb_yes_ignored'] = (
                self.stats.get('bb_yes_ignored', 0) + 1)
        else:
            self.stats['bb_unknown'] += 1
        return None

    def _probe(self, h):
        from sage import lp_branch_decide
        if self.cap_first:
            r0 = lp_branch_decide(self.inst, h,
                                  nodecap=self.cap_first,
                                  depthcap=self.bb_depthcap)
            out0 = self._handle_bb(h, r0)
            if out0 is not None:
                return out0
        rr = None
        if self.use_rr:
            rr = rr_ub(self.inst, h, samples=self.rr_samples,
                       seed=self.rr_seed, nseeds=self.rr_seeds)
            self.rr_evals += rr['samples']
            self.rr_t += rr['t']
            if rr['ok']:
                s, m = rr['schedule'], rr['machine']
                self.rr_yes += 1
                self.stats['rr_yes'] += 1
                cmax = max(s[i] + self.inst['p'][i]
                           for i in range(self.inst['n']))
                return True, (s, m, cmax)
            self.rr_no += 1
            self.stats['rr_no'] += 1

        if self.use_bb:
            r = lp_branch_decide(self.inst, h,
                                 nodecap=self.bb_nodecap,
                                 depthcap=self.bb_depthcap)
            out = self._handle_bb(h, r)
            if out is not None:
                return out

        if self.use_ig and rr is not None and rr.get('best') is not None:
            for k in range(self.ig_seeds):
                ig = ig_ub(self.inst, h, rr['best'],
                           budget=self.ig_budget, seed=self.rr_seed + k)
                self.ig_evals += ig['evals']
                self.ig_t += ig['t']
                if ig['ok']:
                    s, m = ig['schedule'], ig['machine']
                    self.ig_yes += 1
                    self.stats['ig_yes'] += 1
                    cmax = max(s[i] + self.inst['p'][i]
                               for i in range(self.inst['n']))
                    return True, (s, m, cmax)
            self.ig_no += 1
            self.stats['ig_no'] += 1

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
    r['rr_yes'] = getattr(co, 'rr_yes', 0)
    r['rr_no'] = getattr(co, 'rr_no', 0)
    r['ig_yes'] = getattr(co, 'ig_yes', 0)
    r['ig_no'] = getattr(co, 'ig_no', 0)
    r['rr_evals'] = getattr(co, 'rr_evals', 0)
    r['ig_evals'] = getattr(co, 'ig_evals', 0)
    r['rr_t'] = round(getattr(co, 'rr_t', 0.0), 4)
    r['ig_t'] = round(getattr(co, 'ig_t', 0.0), 4)
    r['ok'] = bool(r['certified'] and r['opt'] == known
                   and r['audit'] and r['proof']
                   and r['cert_h'] == known - 1)
    return r
