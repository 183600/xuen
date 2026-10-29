"""v9.0 ROUND-PACT: deterministic LP-rounding portfolio with complete fallback.

The YES side of a fixed-h probe is decided by a small portfolio of
deterministic serial-SGS priority rules read off the root LP.  If any
rule produces a replayed schedule at h, the whole search subtree is
pruned; otherwise PACT's complete decision procedure runs unchanged.
The NO side is therefore untouched: every NO proof is still a PACT
BranchProof and the total trace still replays the whole bracket.

This is the deterministic counterpart of KARST's kernel sampler.  The
portfolio is ordered by a fixed prior learned on the 252-instance corpus
(latest LP support, median, mode, mean, earliest, tail); it is a
sufficient YES test, not a completeness-critical component.
"""
import sys
import time

sys.path[:0] = ['exp/v9z', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from pact import PACT, pact_decide, _integral_schedule, _elig_aware
from sdecc import SDLP
from po import heads_tails
from cab import _greedy_rank
from rdf import check_schedule

RULES = ('lplatest', 'lpmedian', 'lpmode', 'latest', 'est', 'tail', 'lpmean')


def _root(inst, h):
    n = inst['n']
    elig = _elig_aware(inst)
    est, q = heads_tails(inst, 0, [0] * n)
    lp = SDLP(inst, h, est, q, use_dom=True, elig_aware=elig)
    base = [(0, 1)] * lp.N
    return lp, base, lp.solve(), est, q


def _dist(lp, res):
    n = lp.inst['n']
    d = [dict() for _ in range(n)]
    for c, key in enumerate(lp.cols):
        v = res.x[c]
        if v > 1e-9:
            i, t = key[0], key[-1]
            d[i][t] = d[i].get(t, 0.0) + v
    return d


def _order(inst, h, est, q, d, rule):
    n = inst['n']
    p = inst['p']
    latest = [h - q[i] - p[i] for i in range(n)]

    def lp_stat(kind, i):
        dd = d[i]
        if not dd:
            return latest[i]
        tot = sum(dd.values())
        if kind == 'mode':
            return max(dd.items(), key=lambda kv: kv[1])[0]
        if kind == 'mean':
            return sum(t * v for t, v in dd.items()) / max(tot, 1e-12)
        if kind == 'median':
            acc = 0.0
            for t in sorted(dd):
                acc += dd[t]
                if acc >= 0.5 * tot:
                    return t
            return max(dd)
        if kind == 'latest':
            return max(dd)
        return latest[i]

    if rule == 'lplatest':
        return {i: lp_stat('latest', i) + 1e-6 * i for i in range(n)}
    if rule == 'lpmedian':
        return {i: lp_stat('median', i) + 1e-6 * i for i in range(n)}
    if rule == 'lpmode':
        return {i: lp_stat('mode', i) + 1e-6 * i for i in range(n)}
    if rule == 'lpmean':
        return {i: lp_stat('mean', i) + 1e-6 * i for i in range(n)}
    if rule == 'latest':
        return {i: latest[i] + 1e-6 * i for i in range(n)}
    if rule == 'est':
        return {i: est[i] + 1e-6 * i for i in range(n)}
    if rule == 'tail':
        return {i: -q[i] + 1e-6 * i for i in range(n)}
    raise ValueError(rule)


def round_schedule(inst, h, lp=None, res=None, est=None, q=None,
                   rules=RULES):
    """Try each deterministic priority; return (schedule, machine, cmax,
    rule, trials) or (None, None, None, None, trials)."""
    t0 = time.time()
    if lp is None or res is None or est is None or q is None:
        lp, base, res, est, q = _root(inst, h)
    if res.status != 0:
        return dict(schedule=None, machine=None, cmax=None, rule=None,
                    trials=0, lp=lp, res=res, t=round(time.time() - t0, 5))
    n = inst['n']
    got = _integral_schedule(inst, lp, res.x, _elig_aware(inst))
    if got is not None:
        s, m = got
        cmax = max(s[i] + inst['p'][i] for i in range(n))
        if cmax <= h and check_schedule(inst, cmax, s, m):
            return dict(schedule=s, machine=m, cmax=cmax, rule='root-lp',
                        trials=0, lp=lp, res=res,
                        t=round(time.time() - t0, 5))
    d = _dist(lp, res)
    for j, rule in enumerate(rules):
        rank = _order(inst, h, est, q, d, rule)
        g = _greedy_rank(inst, rank)
        if g is not None:
            s, m, cmax = g
            if cmax <= h and check_schedule(inst, cmax, s, m):
                return dict(schedule=s, machine=m, cmax=cmax, rule=rule,
                            trials=j + 1, lp=lp, res=res,
                            t=round(time.time() - t0, 5))
    return dict(schedule=None, machine=None, cmax=None, rule=None,
                trials=len(rules), lp=lp, res=res,
                t=round(time.time() - t0, 5))


class RoundPACT(PACT):
    def __init__(self, inst, round_rules=RULES, **kw):
        kw.setdefault('pact_mode', 'complete')
        kw.setdefault('use_ga', False)
        super().__init__(inst, **kw)
        self.round_rules = tuple(round_rules)
        self.round_lp = 0
        self.round_trials = 0
        self.round_yes = 0
        self.round_fail = 0
        self.round_hits = {}
        self.stats.update(round_lp=0, round_trials=0, round_yes=0,
                          round_fail=0)

    def _probe(self, h):
        n = self.inst['n']
        got = round_schedule(self.inst, h, rules=self.round_rules)
        self.round_lp += 1
        self.stats['round_lp'] = self.round_lp
        self.round_trials += got['trials']
        self.stats['round_trials'] = self.round_trials
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
        lp = got['lp']
        res = got['res']
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
        r['round_lp'] = self.round_lp
        r['round_trials'] = self.round_trials
        r['round_yes'] = self.round_yes
        r['round_fail'] = self.round_fail
        r['round_hits'] = dict(self.round_hits)
        return r


def run_round(inst, known, name, idx, **kw):
    t0 = time.time()
    co = RoundPACT(inst, **kw)
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
