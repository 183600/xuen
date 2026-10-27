"""Loose-start corpus: keep only the cheap valid initialization.

PACT's production initial_bounds already performs LP pin, LNS and STAB,
which on the 252-instance corpus leaves a gap of only 0/1/5.  That makes
outer probe-policy experiments degenerate.  Here we deliberately keep
only the certified critical-path / load lower bound and a greedy
schedule, so the same instances have gaps 0..13.  Correctness is
unchanged: the lower bound still comes with a NO(L-1) proof and the
greedy schedule is checked.
"""
import sys
import time

sys.path[:0] = ['exp/v9talc', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from chip import (base_corpus, pert_corpus, stress_corpus, base_bounds)
from pact import pact_decide
from rdf import check_schedule
from talc import cmax


def rows():
    for tag, rs in (('base', base_corpus()),
                    ('pert', pert_corpus()),
                    ('stress', stress_corpus())):
        for row in rs:
            if len(row) == 4:
                name, idx, inst, opt = row
            else:
                idx, opt, inst = row
                name = tag
            yield tag, name, idx, inst, opt


def init_loose(inst):
    lb, ub, sched, mach, est, q = base_bounds(inst)
    if ub is None:
        return None
    if sched is None or mach is None or not check_schedule(
            inst, ub, sched, mach):
        return None
    r = pact_decide(inst, lb - 1, depthcap=None, nodecap=None)
    proof = r['proof'] if r['verdict'] is False else None
    if proof is None:
        return None
    return dict(L=int(lb), U=int(ub), schedule=list(sched),
                machine=list(mach), proof=proof,
                init_lp=int(r.get('lp_solves', 0)),
                est=est, q=q)


def static_features(inst, est=None, q=None):
    n, m, p = inst['n'], inst['m'], inst['p']
    if est is None or q is None:
        from po import heads_tails
        est, q = heads_tails(inst, 0, [0] * n)
    cp = max(est[i] + p[i] + q[i] for i in range(n))
    work = sum(p)
    edges = sum(len(inst['succ'][i]) for i in range(n))
    slots = sum(len(set(inst['elig'][i])) for i in range(n))
    return dict(n=n, m=m, cp=cp, work=work, maxp=max(p),
                meanp=work / max(1, n), edges=edges,
                edge_density=edges / max(1, n * (n - 1) / 2),
                elig_slots=slots, elig_frac=slots / max(1, n * m),
                work_over_cp=work / max(1, cp),
                work_over_mcp=work / max(1, m * cp))


def state_features(sf, L0, U0, a, b):
    cp = max(1, sf['cp'])
    d = dict(sf)
    d.update(gap=b - a, a=a, b=b, a_minus_L0=a - L0,
             U0_minus_b=U0 - b,
             a_over_cp=a / cp, b_over_cp=b / cp,
             L0_over_cp=L0 / cp, U0_over_cp=U0 / cp,
             work_over_mb=sf['work'] / max(1, sf['m'] * b),
             lower_slack=a - sf['cp'],
             upper_slack=U0 - b,
             gap_over_L=max(0, b - a) / max(1, a))
    return d


def probe_table(inst, L, U):
    tab = {}
    for h in range(L, U):
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        v = r.get('verdict')
        tab[h] = dict(verdict=(None if v is None else bool(v)),
                      cmax=(cmax(inst, r['schedule'])
                            if v is True else None),
                      lp=int(r.get('lp_solves', 0)),
                      nodes=int(r.get('nodes', 0)),
                      cert_lp=int(r.get('cert_lp', 0)),
                      t=float(r.get('t', 0.0)))
    return tab


def dp_table(tab, L, U, actions='all'):
    dp = {}

    def best(a, b):
        if a >= b:
            return 0, None
        key = (a, b)
        if key in dp:
            return dp[key]
        if actions == 'all':
            cand = range(a, b)
        else:
            cand = sorted(set([a, (a + b) // 2, b - 1]))
        val = None
        for h in cand:
            r = tab.get(h)
            if r is None or r['verdict'] is None:
                continue
            if r['verdict'] is False:
                nxt = (h + 1, b)
            else:
                nxt = (a, min(b, r['cmax']))
            sub = best(*nxt)
            if sub[0] is None:
                continue
            c = r['lp'] + sub[0]
            if val is None or c < val[0]:
                val = (c, h)
        dp[key] = (None if val is None else val[0],
                   None if val is None else val[1])
        return dp[key]

    best(L, U)
    return dp


def replay_policy(tab, L, U, choose, max_probes=64):
    a, b = L, U
    probes = 0
    lp = 0
    hist = []
    while a < b and probes < max_probes:
        h = choose(a, b)
        r = tab.get(h)
        if r is None or r['verdict'] is None:
            return dict(closed=False, L=a, U=b, probes=probes, lp=lp,
                        reason='unknown', hist=hist)
        lp += r['lp']
        probes += 1
        hist.append(dict(h=h, yes=r['verdict'], lp=r['lp']))
        if r['verdict'] is False:
            a = h + 1
        else:
            b = min(b, r['cmax'])
    return dict(closed=(a == b), L=a, U=b, probes=probes, lp=lp,
                reason='ok', hist=hist)


def fixed_policy(name):
    first = {'v': True}

    def choose(a, b):
        if name == 'lower-first':
            h = a if first['v'] else (a + b) // 2
        elif name == 'upper-first':
            h = b - 1
        elif name == 'binary':
            h = (a + b) // 2
        elif name == 'pact':
            h = a if b - a <= 4 else (a + b) // 2
        else:
            raise ValueError(name)
        first['v'] = False
        return h

    return choose


def replay_fixed(tab, L, U, name):
    return replay_policy(tab, L, U, fixed_policy(name))
