"""v9.1 SGPACT: gap-guided restart local search on PACT's YES side.

SGPACT keeps PACT-ALC's bracket, exact NO search, CHD fallback and
TotalTrace.  At every probe it first searches the *priority space* of
serial SGS rather than the start-time space of min-conflicts:

  * stage 1: a small random priority portfolio (default 24 samples);
  * stage 2: if the best sampled makespan is h+1, resample with a larger
    budget (default 192 samples);
  * stage 3: if the best gap is at least 2, try a medium portfolio
    (default 384 samples).

Only when sampling fails does the probe run the complete PACT tree
(whose first certificate step is the root LP).

The gap c-h is a cheap upper-bound signal: c==h is an immediate YES,
c==h+1 is the ambiguous band that contains both YES and NO, and c>=h+2
is rare on the 252-case corpus.  Sampling is a local search over the
permutation encoding, decoded by _greedy_rank.  Every accepted schedule
is re-checked by check_schedule; a failed search falls back to the
complete PACT tree, so SGPACT never emits an unverified YES or a NO.

The Fenwick profile from v9.0 LSPACT (exp/v8s/lspact.py) remains the
optional repair substrate; at 1600 iterations it bought 11 extra YES
on 252 cases but cost about 28.7 s, so the default SGPACT configuration
does not run it.  This is recorded as an ablation in the artifact.
"""
import sys
import time
import random

sys.path[:0] = ['exp/v8s', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from pact import PACT, pact_decide
from lspact import _sgs_init
from rdf import check_schedule


class SGPACT(PACT):
    def __init__(self, inst, tries1=24, tries2=192, tries3=384,
                 seed0=9173, **kw):
        super().__init__(inst, **kw)
        self.tries1 = tries1
        self.tries2 = tries2
        self.tries3 = tries3
        self.seed0 = seed0
        self.sgs_calls = 0
        self.sgs_tries = 0
        self.sgs_yes = 0
        self.sgs_time = 0.0
        self.stage1 = 0
        self.stage2 = 0
        self.stage3 = 0
        self.stats.update(sgs_calls=0, sgs_tries=0, sgs_yes=0,
                          stage1=0, stage2=0, stage3=0)

    def _probe(self, h):
        # Sampling is cheap and gives verified YES; it runs before the LP.
        rng = random.Random(self.seed0 + 131 * h + self.sgs_calls)
        best = None
        t0 = time.time()

        def run(tries, stage):
            nonlocal best
            g = _sgs_init(self.inst, h, rng, tries=tries)
            self.sgs_calls += 1
            self.sgs_tries += tries
            self.stats['sgs_calls'] += 1
            self.stats['sgs_tries'] += tries
            self.stats[stage] += 1
            if g is not None and (best is None or g[2] < best[2]):
                best = g
            return g is not None and g[2] <= h

        if run(self.tries1, 'stage1'):
            self.stage1 += 1
        elif best is not None and best[2] == h + 1:
            if run(self.tries2, 'stage2'):
                self.stage2 += 1
        elif best is not None and best[2] >= h + 2:
            if run(self.tries3, 'stage3'):
                self.stage3 += 1
        self.sgs_time += time.time() - t0

        if best is not None and best[2] <= h:
            s, m, c = best
            if check_schedule(self.inst, h, s, m):
                self.sgs_yes += 1
                self.stats['sgs_yes'] += 1
                self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                       cmax=c, engine='sgs'))
                return True, (s, m, c)

        # Sampling failed: complete PACT tree decides YES/NO.
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
        r['sgs_calls'] = self.sgs_calls
        r['sgs_tries'] = self.sgs_tries
        r['sgs_yes'] = self.sgs_yes
        r['sgs_time'] = round(self.sgs_time, 4)
        r['stage1'] = self.stage1
        r['stage2'] = self.stage2
        r['stage3'] = self.stage3
        return r


def run_sgpact(inst, known, name, idx, **kw):
    t0 = time.time()
    co = SGPACT(inst, **kw)
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
