"""v9.0 KARST-ALC: kernelized amortized randomized shortest-path search.

KARST keeps PACT's bracket and complete NO search.  It changes the YES
side: before asking the complete decision procedure, it draws a small
number of *kernel assignments* from the root LP and expands each one by a
serial SGS (a longest-path decoder).  The kernel is the fractional support
of the root LP vertex; jobs that are integral in the vertex keep their LP
start as a priority.  The sampler is a Las Vegas speedup, not a
correctness-critical component:

  * a sampled schedule is accepted only after check_schedule and Cmax <= h;
  * if all samples fail, PACT's complete search decides the probe;
  * NO proofs are still produced by PACT's complete search.

The restart budget is geometric (16, 32, 64, 128 with fresh seeds), so the
work spent before a success is at most a constant factor of the work of
the successful round (universal / amortized restarts).
"""
import sys
import time
import random

sys.path[:0] = ['exp/v9y', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from pact import (PACT, pact_decide, _integral_schedule,
                  _elig_aware)
from sdecc import SDLP
from po import heads_tails
from cab import _greedy_rank
from rdf import check_schedule


def _root_lp(inst, h):
    n = inst['n']
    elig = _elig_aware(inst)
    est, q = heads_tails(inst, 0, [0] * n)
    lp = SDLP(inst, h, est, q, use_dom=True, elig_aware=elig)
    base = [(0, 1)] * lp.N
    return lp, base, lp.solve(base), est, q


def _distributions(lp, res):
    """Per-job start-time mass and the LP-integral start (or None)."""
    n = lp.inst['n']
    dist = [dict() for _ in range(n)]
    for c, key in enumerate(lp.cols):
        v = res.x[c]
        if v <= 1e-9:
            continue
        i, t = key[0], key[-1]
        dist[i][t] = dist[i].get(t, 0.0) + v
    integral = [None] * n
    support = []
    for i in range(n):
        d = dist[i]
        if not d:
            integral[i] = None
            support.append(i)
            continue
        top_t, top_v = max(d.items(), key=lambda kv: kv[1])
        if top_v >= 1 - 1e-6 and sum(v for t, v in d.items()
                                     if t != top_t) <= 1e-6:
            integral[i] = top_t
        else:
            support.append(i)
    return dist, integral, support


def _pick(d, total, u):
    acc = 0.0
    for t in sorted(d):
        acc += d[t]
        if acc >= u * total:
            return t
    return max(d)


def karst_sample(inst, h, lp, res, mode='support',
                 budgets=(16, 32, 64, 128), seed0=20261025):
    """Sample kernel assignments and expand them with a longest-path SGS.

    Returns dict(schedule, machine, trials, support, integral, rounds,
    success_round, t).  schedule/machine are None on failure.
    """
    t0 = time.time()
    n = inst['n']
    dist, integral, support = _distributions(lp, res)
    if any(not dist[i] for i in range(n)):
        return dict(schedule=None, machine=None, trials=0,
                    support=len(support), integral=0, rounds=0,
                    success_round=None, t=round(time.time() - t0, 5))
    trials = 0
    rounds = 0
    for r, B in enumerate(budgets):
        rounds = r + 1
        rng = random.Random(seed0 + 1009 * r + 97 * h
                            + 13 * n + 7 * len(inst['p']))
        for _ in range(B):
            rank = [0.0] * n
            for i in range(n):
                if mode == 'support' and integral[i] is not None:
                    t = integral[i]
                else:
                    d = dist[i]
                    total = sum(d.values())
                    if total <= 1e-12:
                        t = 0
                    else:
                        t = _pick(d, total, rng.random())
                rank[i] = t + rng.random() * 1e-6
            got = _greedy_rank(inst, rank)
            trials += 1
            if got is None:
                continue
            s, m, cmax = got
            if cmax <= h and check_schedule(inst, cmax, s, m):
                return dict(schedule=s, machine=m, trials=trials,
                            support=len(support),
                            integral=sum(1 for x in integral
                                         if x is not None),
                            rounds=rounds, success_round=r,
                            t=round(time.time() - t0, 5))
    return dict(schedule=None, machine=None, trials=trials,
                support=len(support),
                integral=sum(1 for x in integral if x is not None),
                rounds=rounds, success_round=None,
                t=round(time.time() - t0, 5))


class KARST(PACT):
    def __init__(self, inst, karst_mode='support',
                 karst_budgets=(16, 32, 64, 128), karst_seed=20261025,
                 **kw):
        kw.setdefault('pact_mode', 'complete')
        kw.setdefault('use_ga', False)
        super().__init__(inst, **kw)
        self.karst_mode = karst_mode
        self.karst_budgets = tuple(karst_budgets)
        self.karst_seed = karst_seed
        self.karst_lp = 0
        self.karst_trials = 0
        self.karst_yes = 0
        self.karst_fail = 0
        self.karst_support_sum = 0
        self.karst_support_max = 0
        self.karst_success = []
        self.stats.update(karst_lp=0, karst_trials=0, karst_yes=0,
                          karst_fail=0, karst_support_sum=0,
                          karst_support_max=0)

    def _probe(self, h):
        n = self.inst['n']
        lp, base, res, est, q = _root_lp(self.inst, h)
        self.karst_lp += 1
        self.stats['karst_lp'] = self.karst_lp

        # 1. Cheap exact hit: the root LP already decoded to a schedule.
        if res.status == 0:
            got = _integral_schedule(self.inst, lp, res.x,
                                     _elig_aware(self.inst))
            if got is not None:
                s, m = got
                cmax = max(s[i] + self.inst['p'][i] for i in range(n))
                if cmax <= h and check_schedule(self.inst, cmax, s, m):
                    self.stats['karst_yes'] += 1
                    self.karst_yes += 1
                    self.steps.append(dict(h=h, v=True, schedule=s,
                                           machine=m, cmax=cmax,
                                           engine='root-lp'))
                    return True, (s, m, cmax)

        # 2. Kernel sampling.  Only a feasible root LP can yield a YES.
        if res.status == 0:
            got = karst_sample(self.inst, h, lp, res,
                               mode=self.karst_mode,
                               budgets=self.karst_budgets,
                               seed0=self.karst_seed)
            self.karst_trials += got['trials']
            self.stats['karst_trials'] = self.karst_trials
            self.karst_support_sum += got['support']
            self.karst_support_max = max(self.karst_support_max,
                                         got['support'])
            self.stats['karst_support_sum'] = self.karst_support_sum
            self.stats['karst_support_max'] = self.karst_support_max
            if got['schedule'] is not None:
                s, m = got['schedule'], got['machine']
                cmax = max(s[i] + self.inst['p'][i] for i in range(n))
                if cmax <= h and check_schedule(self.inst, cmax, s, m):
                    self.karst_yes += 1
                    self.stats['karst_yes'] += 1
                    self.karst_success.append(dict(
                        h=h, trials=got['trials'],
                        support=got['support'],
                        success_round=got['success_round']))
                    self.steps.append(dict(h=h, v=True, schedule=s,
                                           machine=m, cmax=cmax,
                                           engine='karst',
                                           trials=got['trials']))
                    return True, (s, m, cmax)
            self.karst_fail += 1
            self.stats['karst_fail'] += 1

        # 3. Complete PACT fallback (sound and complete).
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
        # Extremely rare: complete search returned UNKNOWN.  Use CHD.
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
        r['karst_lp'] = self.karst_lp
        r['karst_trials'] = self.karst_trials
        r['karst_yes'] = self.karst_yes
        r['karst_fail'] = self.karst_fail
        r['karst_support_avg'] = round(
            self.karst_support_sum / max(1, self.karst_yes
                                         + self.karst_fail), 3)
        r['karst_support_max'] = self.karst_support_max
        r['karst_success'] = list(self.karst_success)
        return r


def run_karst(inst, known, name, idx, **kw):
    t0 = time.time()
    co = KARST(inst, **kw)
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
