"""v9.0 DSC-ALC: deterministic sampling with certificates.

Builds on v8.9 PACT-ALC.  The new layer is a *one-sided* deterministic
sampler:

    sample_yes(inst, h, B) -> YES(schedule) or NO-SAMPLE (no verdict)

It solves the fixed-h SDLP once, reads the per-job marginal distribution
of start times, and draws B start-time vectors from a deterministic
low-discrepancy (Halton) sequence.  Each vector is turned into a priority
order and decoded by a serial SGS; only a schedule that passes
check_schedule is accepted.  A failed sample is *not* a NO proof.  If the
sampler misses, the probe falls back to PACT's complete certificate
search, which supplies NO or YES with a replayable proof.

The sampler is therefore sound independently of the sampling
distribution: it can only add YES facts, never NO facts.  Determinism
comes from the fixed Halton sequence and deterministic tie-breaking.
"""
import sys
import time
import math

sys.path[:0] = ['exp/v9s', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from pact import PACT, pact_decide
from sage import _elig_aware
from sdecc import SDLP
from po import heads_tails
from rdf import check_schedule
from cab import _greedy_rank


def _primes(n):
    out = []
    x = 2
    while len(out) < n:
        if all(x % p for p in out if p * p <= x):
            out.append(x)
        x += 1
    return out


def _vdc(k, base):
    v = 0.0
    inv = 1.0 / base
    while k:
        v += (k % base) * inv
        k //= base
        inv /= base
    return v


def _halton(k, bases, shift):
    return [(_vdc(k, b) + s) % 1.0 for b, s in zip(bases, shift)]


def _marginals(lp, z, est):
    n = lp.n
    dist, times = [], []
    for i in range(n):
        d = {}
        for c, key in enumerate(lp.cols):
            if key[0] == i and z[c] > 1e-9:
                d[key[-1]] = d.get(key[-1], 0.0) + z[c]
        mass = sum(d.values())
        if mass <= 1e-12:
            d = {est[i]: 1.0}
            mass = 1.0
        cdf, acc = [], 0.0
        for t, v in sorted(d.items()):
            acc += v / mass
            cdf.append((t, acc))
        if cdf:
            cdf[-1] = (cdf[-1][0], 1.0)
        dist.append(cdf)
        times.append([t for t, _ in cdf])
    return dist, times


def _draw(cdf, times, u, uniform=False):
    if uniform:
        return times[min(len(times) - 1, int(u * len(times)))]
    for t, c in cdf:
        if u <= c:
            return t
    return cdf[-1][0]


def sample_yes(inst, h, budget=64, diversify=True, mode='halton',
               seed=0, uniform_mix=8, return_lp=False, source='lp',
               rotation=True):
    """Deterministic LP-guided sampling.  Returns a dict.

    verdict True  -> schedule/machine checked at h
    verdict None  -> no YES found (never a NO claim)
    """
    t0 = time.time()
    n, m, p = inst['n'], inst['m'], inst['p']
    est, q = heads_tails(inst, 0, [0] * n)
    elig = _elig_aware(inst)
    lp = SDLP(inst, h, est, q, use_dom=True, elig_aware=elig)
    res = lp.solve()
    st = dict(verdict=None, schedule=None, machine=None, cmax=None,
              samples=0, hit=None, best=10 ** 9, root=res.status,
              lp_solves=1, t=0.0, mode=mode, source=source, lp=lp, res=res)
    if res.status != 0:
        st['t'] = round(time.time() - t0, 5)
        return st
    z = res.x
    # integral root: decode directly
    starts = [None] * n
    machs = [None] * n
    for c, key in enumerate(lp.cols):
        if z[c] > 1 - 1e-7:
            i, t = key[0], key[-1]
            if starts[i] is not None:
                starts = None
                break
            starts[i] = t
            if elig:
                machs[i] = key[1]
    if starts is not None and all(x is not None for x in starts):
        if not elig:
            from pact import _assign_machines
            machs = _assign_machines(inst, starts)
        if machs is not None:
            cmax = max(starts[i] + p[i] for i in range(n))
            if cmax <= h and check_schedule(inst, h, starts, machs):
                st.update(verdict=True, schedule=starts, machine=machs,
                          cmax=cmax, hit=0, best=cmax)
                st['t'] = round(time.time() - t0, 5)
                return st
    dist, times = _marginals(lp, z, est)
    bases = _primes(max(1, n))
    shift = ([((i + 1) * 0.6180339887498949) % 1.0 for i in range(n)]
             if rotation else [0.0] * n)
    for k in range(1, budget + 1):
        if mode == 'random':
            # deterministic LCG, used only as a reproducibility baseline
            x = (seed * 6364136223846793005 + k * 1442695040888963407) & ((1 << 64) - 1)
            u = []
            for _ in range(n):
                x = (x * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
                u.append((x >> 11) / float(1 << 53))
        elif mode == 'uniform':
            u = [(k * (i + 1) * 0.6180339887498949) % 1.0 for i in range(n)]
        else:
            u = _halton(k, bases, shift)
        rank = {}
        for i in range(n):
            uni = ((source == 'uniform')
                   or (diversify and (uniform_mix > 0)
                       and (k % uniform_mix == 0)))
            t = _draw(dist[i], times[i], u[i], uniform=uni)
            rank[i] = t + 1e-6 * (((i * 2654435761) % 997) / 997.0)
        g = _greedy_rank(inst, rank)
        st['samples'] = k
        if g is None:
            continue
        s, mm, cmax = g
        if cmax < st['best']:
            st['best'] = cmax
        if cmax <= h and check_schedule(inst, h, s, mm):
            st.update(verdict=True, schedule=s, machine=mm, cmax=cmax,
                      hit=k, rank=dict(rank))
            st['t'] = round(time.time() - t0, 5)
            return st
    st['t'] = round(time.time() - t0, 5)
    return st



def audit_sample(inst, h, rank, schedule, machine):
    """Replay a sample witness: SGS(rank) must reproduce the schedule."""
    g = _greedy_rank(inst, rank)
    if g is None:
        return False
    s, m, cmax = g
    if list(s) != list(schedule) or list(m) != list(machine):
        return False
    return cmax <= h and bool(check_schedule(inst, h, s, m))


class DSC(PACT):
    """PACT with a deterministic one-sided sampling phase."""

    def __init__(self, inst, sample_budget=64, sample_mode='halton',
                 sample_first=True, diversify=True, uniform_mix=8,
                 sample_source='lp', **kw):
        kw.setdefault('pact_depth', None)
        kw.setdefault('use_ga', False)
        kw.setdefault('complete_fallback', True)
        super().__init__(inst, **kw)
        self.sample_budget = sample_budget
        self.sample_mode = sample_mode
        self.sample_first = sample_first
        self.diversify = diversify
        self.uniform_mix = uniform_mix
        self.sample_source = sample_source
        self.sample_calls = 0
        self.sample_lp = 0
        self.sample_hits = 0
        self.sample_misses = 0
        self.sample_samples = 0
        self.sample_hit_sum = 0
        self.sample_stats = []
        self.sample_witnesses = []
        self.sample_audit = True

    def _probe(self, h):
        if not self.sample_first or self.sample_budget <= 0:
            return super()._probe(h)
        r = sample_yes(self.inst, h, budget=self.sample_budget,
                       diversify=self.diversify,
                       mode=self.sample_mode,
                       uniform_mix=self.uniform_mix,
                       return_lp=True, source=self.sample_source)
        self.sample_calls += 1
        self.sample_lp += r['lp_solves']
        self.sample_samples += r['samples']
        self.sample_stats.append(dict(h=h, root=r['root'],
                                      hit=r['hit'],
                                      samples=r['samples'],
                                      best=r['best']))
        if r['verdict'] is True:
            self.sample_hits += 1
            self.sample_hit_sum += r['hit'] or 0
            s, m = r['schedule'], r['machine']
            cmax = r['cmax']
            self.steps.append(dict(h=h, v=True, schedule=s,
                                   machine=m, cmax=cmax,
                                   engine='sample', sample=r['hit'],
                                   rank=r.get('rank')))
            if r.get('rank') is not None:
                self.sample_witnesses.append(
                    dict(h=h, rank=r['rank'], schedule=list(s),
                         machine=list(m)))
            return True, (s, m, cmax)
        self.sample_misses += 1
        # Complete certificate search, reusing the sampler's root LP.
        q = pact_decide(self.inst, h, depthcap=None, nodecap=None,
                        root_lp=r.get('lp'), root_res=r.get('res'))
        self.pact_lp += q['lp_solves']
        self.pact_cert_lp += q.get('cert_lp', 0)
        self.pact_nodes += q['nodes']
        if q['verdict'] is False:
            self.pact_no += 1
            self.stats['pact_no'] += 1
            self._record_proof(q['proof'])
            self.steps.append(dict(h=h, v=False, proof=q['proof'],
                                   engine='complete', root_reused=True))
            return False, q['proof']
        if q['verdict'] is True:
            self.pact_yes += 1
            self.stats['pact_yes'] += 1
            s, m = q['schedule'], q['machine']
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine='complete',
                                   root_reused=True))
            return True, (s, m, cmax)
        # Last resort: CHD.
        self.stats['chd_fallback'] += 1
        v, st, rdf = self._decide(h)
        self.queries += 1
        self._absorb(st)
        self._record(h, v, st)
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
        r['sample_calls'] = self.sample_calls
        r['sample_lp'] = self.sample_lp
        r['sample_hits'] = self.sample_hits
        r['sample_misses'] = self.sample_misses
        r['sample_samples'] = self.sample_samples
        r['sample_hit_sum'] = self.sample_hit_sum
        r['sample_stats'] = self.sample_stats
        self.sample_audit = all(
            audit_sample(self.inst, w['h'], w['rank'], w['schedule'],
                         w['machine'])
            for w in self.sample_witnesses)
        r['sample_witnesses'] = len(self.sample_witnesses)
        r['sample_audit'] = self.sample_audit
        return r


def run_dsc(inst, known, name, idx, **kw):
    from pact import run_pact
    # replicate run_pact with the DSC class
    t0 = time.time()
    co = DSC(inst, **kw)
    r = co.optimize()
    dt = time.time() - t0
    r.update(name=name, idx=idx, known=known, t=round(dt, 4))
    from apex import bound_lb
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
