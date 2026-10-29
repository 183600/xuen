"""v9.0 HYBRID-PACT: deterministic rounding + kernel sampling + complete fallback.

At each fixed-h probe:
  1. solve the root SDLP once;
  2. try a deterministic LP-rounding portfolio (cheap, no random trials);
  3. if it fails, run KARST's kernel sampler on the same root LP;
  4. if it still fails, run PACT's complete certificate search (NO or YES).
NO proofs and the total trace are inherited unchanged.
"""
import sys
import time

sys.path[:0] = ['exp/v9z', 'exp/v9y', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from pact import PACT, pact_decide, _integral_schedule, _elig_aware
from pact_round import round_schedule, _root, RULES
from karst import karst_sample
from rdf import check_schedule


class HybridPACT(PACT):
    def __init__(self, inst, round_rules=RULES,
                 karst_budgets=(16, 32, 64, 128), karst_mode='support',
                 karst_seed=20261025, **kw):
        kw.setdefault('pact_mode', 'complete')
        kw.setdefault('use_ga', False)
        super().__init__(inst, **kw)
        self.round_rules = tuple(round_rules)
        self.karst_budgets = tuple(karst_budgets)
        self.karst_mode = karst_mode
        self.karst_seed = karst_seed
        self.root_lp_count = 0
        self.round_yes = 0
        self.round_fail = 0
        self.karst_yes = 0
        self.karst_fail = 0
        self.karst_trials = 0
        self.round_hits = {}
        self.stats.update(root_lp=0, round_yes=0, round_fail=0,
                          karst_yes=0, karst_fail=0, karst_trials=0)
        self.narrow_hook = None

    def _probe(self, h):
        n = self.inst['n']
        lp, base, res, est, q = _root(self.inst, h)
        self.root_lp_count += 1
        self.stats['root_lp'] = self.root_lp_count
        # 1. deterministic rounding
        got = round_schedule(self.inst, h, lp=lp, res=res, est=est, q=q,
                             rules=self.round_rules)
        if got['schedule'] is not None:
            s, m = got['schedule'], got['machine']
            cmax = got['cmax']
            self.round_yes += 1
            self.stats['round_yes'] += 1
            r = got['rule']
            self.round_hits[r] = self.round_hits.get(r, 0) + 1
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine='round', rule=r))
            return True, (s, m, cmax)
        self.round_fail += 1
        self.stats['round_fail'] += 1
        # 2. kernel sampling
        if res.status == 0:
            ks = karst_sample(self.inst, h, lp, res,
                              mode=self.karst_mode,
                              budgets=self.karst_budgets,
                              seed0=self.karst_seed)
            self.karst_trials += ks['trials']
            self.stats['karst_trials'] = self.karst_trials
            if ks['schedule'] is not None:
                s, m = ks['schedule'], ks['machine']
                cmax = max(s[i] + self.inst['p'][i] for i in range(n))
                if cmax <= h and check_schedule(self.inst, cmax, s, m):
                    self.karst_yes += 1
                    self.stats['karst_yes'] += 1
                    self.steps.append(dict(h=h, v=True, schedule=s,
                                           machine=m, cmax=cmax,
                                           engine='karst',
                                           trials=ks['trials']))
                    return True, (s, m, cmax)
            self.karst_fail += 1
            self.stats['karst_fail'] += 1
        # 2b. optional narrow-pivot hook (runs only on a closing probe)
        if self.narrow_hook is not None and self.opt - self.lb == 1:
            got = self.narrow_hook(h, lp, res, est, q)
            if got is not None:
                return got
        # 3. complete search
        reuse = res.status in (0, 2)
        r = pact_decide(self.inst, h, depthcap=None, nodecap=None,
                        root_lp=lp if reuse else None,
                        root_res=res if reuse else None)
        self.pact_calls += 1
        self.pact_lp += r['lp_solves'] + (1 if reuse else 0)
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
            cmax = max(s[i] + self.inst['p'][i] for i in range(n))
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine='complete'))
            return True, (s, m, cmax)
        self.pact_unknown += 1
        self.stats['pact_unknown'] += 1
        self.stats['chd_fallback'] += 1
        v, st, rdf = self._decide(h)
        self.queries += 1
        self._absorb(st)
        self._record(h, v, st)
        if v is False:
            self.steps.append(dict(h=h, v=False, proof=rdf,
                                   engine='chd'))
        elif v is True:
            s, m = rdf.schedule, rdf.machine
            cmax = max(s[i] + self.inst['p'][i] for i in range(n))
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine='chd'))
        else:
            self.steps.append(dict(h=h, v=None, engine='chd'))
        return v, rdf

    def _result(self):
        r = super()._result()
        r['root_lp'] = self.root_lp_count
        r['round_yes'] = self.round_yes
        r['round_fail'] = self.round_fail
        r['karst_yes'] = self.karst_yes
        r['karst_fail'] = self.karst_fail
        r['karst_trials'] = self.karst_trials
        r['round_hits'] = dict(self.round_hits)
        return r


def run_hybrid(inst, known, name, idx, **kw):
    t0 = time.time()
    co = HybridPACT(inst, **kw)
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
