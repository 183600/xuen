"""v9.2 RACE-ALC: adaptive Las Vegas race between kernel sampling and
exact certificate search.

PACT-ALC certifies every fixed-h probe with either a checked schedule
(YES) or a BranchProof/Farkas certificate (NO).  KARST-ALC spends a
fixed geometric sampling budget before falling back to the complete
search.  On hard NO probes every sample is wasted; on hard YES probes
the complete search may be much more expensive than a few more samples.

RACE interleaves the two engines with a doubling schedule

    round r:  B_r samples, then pact_decide(nodecap=C_r),

with B=(16,16,32,64,128) and C=(4,8,16,32,None).  A round that ends in
a verdict returns it immediately.  A capped UNKNOWN is discarded, so the
only effect of interleaving is work duplication, never correctness:
YES schedules are checked by check_schedule and NO trees are emitted
only by a complete pact_decide.  The geometric schedule gives the usual
"run the best engine at most twice" guarantee up to additive constants.

The network-flow and Fenwick components live in the two engines: the
flow/Hall certificate is the NO-side leaf check inherited from PACT, and
the Fenwick profile is used by the local-search sampler arm (LSPACT) when
enabled.  RACE itself is the adaptive scheduler over these components.
"""
import sys
import time

sys.path[:0] = ['exp/v9r', 'exp/v9y', 'exp/v9s', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from karst import (KARST, _root_lp, karst_sample)
from pact import pact_decide, _integral_schedule, _elig_aware
from rdf import check_schedule


class RACE(KARST):
    def __init__(self, inst, race_budgets=(16, 16, 32, 64, 128),
                 race_caps=(5,), race_seed=20261025,
                 **kw):
        kw.setdefault('karst_mode', 'support')
        kw.setdefault('karst_budgets', ())
        super().__init__(inst, **kw)
        self.race_budgets = tuple(race_budgets)
        self.race_caps = tuple(race_caps)
        self.race_seed = race_seed
        self.race_rounds = 0
        self.race_samples = 0
        self.race_cap_unknown = 0
        self.race_sample_yes = 0
        self.race_pact_yes = 0
        self.race_pact_no = 0
        self.race_lp = 0
        self.race_trace = []
        self.stats.update(race_rounds=0, race_samples=0,
                          race_cap_unknown=0, race_sample_yes=0,
                          race_pact_yes=0, race_pact_no=0, race_lp=0,
                          race_trace=[])

    def _accept(self, h, s, m, cmax, engine, extra=None):
        if cmax <= h and check_schedule(self.inst, cmax, s, m):
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine=engine,
                                   **(extra or {})))
            return True, (s, m, cmax)
        return None

    def _probe(self, h):
        n = self.inst['n']
        lp, base, res, est, q = _root_lp(self.inst, h)
        self.karst_lp += 1
        self.stats['karst_lp'] = self.karst_lp

        # 0. The root LP may already decode to a checked nonpreemptive
        #    schedule; this is the cheapest possible YES certificate.
        if res.status == 0:
            got = _integral_schedule(self.inst, lp, res.x,
                                     _elig_aware(self.inst))
            if got is not None:
                s, m = got
                cmax = max(s[i] + self.inst['p'][i] for i in range(n))
                out = self._accept(h, s, m, cmax, 'root-lp')
                if out is not None:
                    self.karst_yes += 1
                    self.stats['karst_yes'] += 1
                    return out

        # 1. Interleaved race.  Rounds are geometric in both directions.
        for r, B in enumerate(self.race_budgets):
            cap = (self.race_caps[r]
                   if r < len(self.race_caps) else None)
            self.race_rounds = r + 1
            self.stats['race_rounds'] = self.race_rounds
            if B > 0 and res.status == 0:
                got = karst_sample(self.inst, h, lp, res,
                                   mode=self.karst_mode,
                                   budgets=(B,),
                                   seed0=self.race_seed + 1009 * r)
                self.karst_trials += got['trials']
                self.race_samples += got['trials']
                self.karst_support_sum += got['support']
                self.karst_support_max = max(self.karst_support_max,
                                             got['support'])
                self.stats['karst_trials'] = self.karst_trials
                self.stats['karst_support_sum'] = self.karst_support_sum
                self.stats['karst_support_max'] = self.karst_support_max
                self.stats['race_samples'] = self.race_samples
                if got['schedule'] is not None:
                    s, m = got['schedule'], got['machine']
                    cmax = max(s[i] + self.inst['p'][i]
                               for i in range(n))
                    out = self._accept(h, s, m, cmax, 'race-sample',
                                       extra=dict(trials=got['trials'],
                                                  cap=cap))
                    if out is not None:
                        self.karst_yes += 1
                        self.race_sample_yes += 1
                        self.stats['karst_yes'] += 1
                        self.stats['race_sample_yes'] += 1
                        self.karst_success.append(dict(
                            h=h, trials=got['trials'],
                            support=got['support'],
                            success_round=r, cap=cap))
                        return out

            # Bounded exact lookahead.  Only the first round uses a
            # cap; later rounds are sampling-only and the complete exact
            # search runs once after the last sampling round.  Deferring
            # the complete search avoids re-solving the same tree.
            if cap is not None:
                reuse = res.status in (0, 2)
                self.race_lp += 1
                rr = pact_decide(self.inst, h, depthcap=None,
                                 nodecap=cap,
                                 root_lp=lp if reuse else None,
                                 root_res=res if reuse else None)
                self.pact_lp += rr['lp_solves'] + (1 if reuse else 0)
                self.pact_cert_lp += rr.get('cert_lp', 0)
                self.pact_nodes += rr['nodes']
                self.stats['race_lp'] = self.race_lp
                if rr['verdict'] is False:
                    self.pact_no += 1
                    self.race_pact_no += 1
                    self.stats['pact_no'] += 1
                    self.stats['race_pact_no'] += 1
                    self._record_proof(rr['proof'])
                    self.steps.append(dict(h=h, v=False,
                                           proof=rr['proof'],
                                           engine='race-pact', cap=cap))
                    return False, rr['proof']
                if rr['verdict'] is True:
                    self.pact_yes += 1
                    self.race_pact_yes += 1
                    self.stats['pact_yes'] += 1
                    self.stats['race_pact_yes'] += 1
                    s, m = rr['schedule'], rr['machine']
                    cmax = max(s[i] + self.inst['p'][i]
                               for i in range(n))
                    self.steps.append(dict(h=h, v=True, schedule=s,
                                           machine=m, cmax=cmax,
                                           engine='race-pact', cap=cap))
                    return True, (s, m, cmax)
                self.race_cap_unknown += 1
                self.stats['race_cap_unknown'] = self.race_cap_unknown
                self.race_trace.append(dict(round=r, cap=cap,
                                            nodes=rr['nodes'],
                                            verdict=None))
                self.stats['race_trace'] = list(self.race_trace)

        # 2. Complete fallback: the last cap is None, so this is normally
        #    unreachable; keep it as a hard soundness backstop.
        reuse = res.status in (0, 2)
        rr = pact_decide(self.inst, h, depthcap=None, nodecap=None,
                         root_lp=lp if reuse else None,
                         root_res=res if reuse else None)
        self.pact_calls += 1
        self.pact_lp += rr['lp_solves'] + (1 if reuse else 0)
        self.pact_cert_lp += rr.get('cert_lp', 0)
        self.pact_nodes += rr['nodes']
        if rr['verdict'] is False:
            self.pact_no += 1
            self.stats['pact_no'] += 1
            self._record_proof(rr['proof'])
            self.steps.append(dict(h=h, v=False, proof=rr['proof'],
                                   engine='complete'))
            return False, rr['proof']
        if rr['verdict'] is True:
            self.pact_yes += 1
            self.stats['pact_yes'] += 1
            s, m = rr['schedule'], rr['machine']
            cmax = max(s[i] + self.inst['p'][i] for i in range(n))
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine='complete'))
            return True, (s, m, cmax)
        self.stats['chd_fallback'] += 1
        v, st, rdf = self._decide(h)
        self.queries += 1
        self._absorb(st)
        self._record(h, v, st)
        return v, rdf

    def _result(self):
        r = super()._result()
        r.update(race_rounds=self.race_rounds,
                 race_samples=self.race_samples,
                 race_cap_unknown=self.race_cap_unknown,
                 race_sample_yes=self.race_sample_yes,
                 race_pact_yes=self.race_pact_yes,
                 race_pact_no=self.race_pact_no,
                 race_lp=self.race_lp,
                 race_trace=list(self.race_trace))
        return r


def run_race(inst, known, name, idx, **kw):
    t0 = time.time()
    co = RACE(inst, **kw)
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
