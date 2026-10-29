"""Generate a large-gap synthetic corpus with exact OPT.

The 252-instance corpus has weak-bound gaps only 0/1/5.  To test the
outer search honestly we generate random small instances and keep those
whose certified critical-path bound is far below a greedy schedule.  OPT
is computed by complete PACT decision probes (binary search) and checked
by NO(OPT-1) plus a feasible schedule of length OPT.
"""
import sys
import json
import random
import time

sys.path[:0] = ['exp/v9i', 'exp/v9m', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8j', 'exp/v8f', 'exp/v8e', 'exp/v8g',
                'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a',
                'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60',
                'exp/v13']

from apex import bound_lb
from chip import chip_bounds
from pact import pact_decide, PACT
from rdf import check_schedule


def gen(n, m, seed, pe, peel):
    rng = random.Random(seed)
    perm = list(range(n))
    rng.shuffle(perm)
    rank = {v: i for i, v in enumerate(perm)}
    p = [rng.randint(1, 9) for _ in range(n)]
    pred = [[] for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if rank[i] < rank[j] and rng.random() < pe:
                pred[j].append(i)
    succ = [[] for _ in range(n)]
    for j in range(n):
        for i in pred[j]:
            succ[i].append(j)
    elig = []
    for i in range(n):
        if rng.random() < peel:
            k = rng.randint(1, m)
            elig.append(sorted(rng.sample(range(m), k)))
        else:
            elig.append(list(range(m)))
    return {'n': n, 'm': m, 'p': p, 'pred': pred, 'succ': succ,
            'elig': elig}


def exact_opt(inst, lo, hi, stats):
    schedule = machine = None
    while lo < hi:
        h = (lo + hi) // 2
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        stats['lp'] += r.get('lp_solves', 0)
        if r['verdict'] is False:
            lo = h + 1
        elif r['verdict'] is True:
            s, m = r['schedule'], r['machine']
            c = max(s[i] + inst['p'][i] for i in range(inst['n']))
            schedule, machine = s, m
            hi = min(hi, c)
        else:
            return None, None, None
    # Verify both sides independently of the binary-search loop.
    rno = pact_decide(inst, lo - 1, depthcap=None, nodecap=None)
    stats['lp'] += rno.get('lp_solves', 0)
    if rno['verdict'] is not False:
        return None, None, None
    if schedule is None:
        # A final YES probe at lo is needed if the loop closed on NO.
        rye = pact_decide(inst, lo, depthcap=None, nodecap=None)
        stats['lp'] += rye.get('lp_solves', 0)
        if rye['verdict'] is not True:
            return None, None, None
        schedule, machine = rye['schedule'], rye['machine']
    c = max(schedule[i] + inst['p'][i] for i in range(inst['n']))
    if c > lo or not check_schedule(inst, c, schedule, machine):
        return None, None, None
    return lo, schedule, machine


def main():
    rng = random.Random(20261026)
    candidates = []
    stats = dict(lp=0)
    t0 = time.time()
    for seed in range(900):
        n = rng.randint(9, 13)
        m = rng.randint(2, 4)
        pe = rng.choice([0.10, 0.15, 0.20, 0.25])
        peel = rng.choice([0.25, 0.35, 0.50])
        inst = gen(n, m, seed, pe, peel)
        b = chip_bounds(inst)
        if b['ub0'] is None:
            continue
        bl = bound_lb(inst)
        ub = b['ub0']
        gap = ub - bl
        if gap < 4:
            continue
        opt, sched, mach = exact_opt(inst, bl, ub, stats)
        if opt is None:
            continue
        co = PACT(inst, pact_mode='complete', use_ga=False)
        plb, pub, _, _ = co.initial_bounds()
        candidates.append(dict(
            seed=seed, n=n, m=m, pe=pe, peel=peel,
            inst=inst, opt=opt, lb_weak=bl, ub0=ub, gap0=gap,
            lb_pact=int(plb), ub_pact=int(pub),
            gap_pact=int(pub - plb)))
        if len(candidates) >= 260:
            break
    # Stratify: keep the first 40 with 4<=gap<=7 and the first 40
    # with gap>=8, so both moderate and large gaps are represented.
    small = [c for c in candidates if c['gap0'] <= 7][:40]
    large = [c for c in candidates if c['gap0'] >= 8][:40]
    keep = small + large
    out = dict(
        generated=len(keep), candidates=len(candidates),
        time=round(time.time() - t0, 2), lp=stats['lp'],
        gap_hist={str(g): sum(1 for c in keep if c['gap0'] == g)
                  for g in sorted(set(c['gap0'] for c in keep))},
        rows=keep)
    with open('exp/v9i/synthetic.json', 'w') as f:
        json.dump(out, f, indent=1)
    print('kept', len(keep), 'candidates', len(candidates),
          'gap hist', out['gap_hist'], 'time', out['time'],
          'lp', out['lp'])


if __name__ == '__main__':
    main()
