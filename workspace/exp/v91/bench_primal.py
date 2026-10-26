"""Compare primal heuristics on the 252-instance corpus.

All candidates are decoded to schedules and replayed by check_schedule.
The comparison is on the upper side only; no NO proof is involved.
"""
import sys
import time
import collections
import json

sys.path[:0] = ['exp/v91', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from cab import _greedy_rank
from chip import base_bounds
from icf import corpora
from lns import lns_drop
from po import heads_tails
from rdf import check_schedule
from sage import ga_schedule
from sparc import Swarm


def portfolio(inst, ub, s0, m0):
    n, p = inst['n'], inst['p']
    est, q = heads_tails(inst, 0, [0] * n)
    latest = [ub - q[i] - p[i] for i in range(n)]
    best, bs, bm = ub, s0, m0
    for key in (lambda i: est[i], lambda i: latest[i],
                lambda i: -q[i], lambda i: est[i] - 0.5 * q[i]):
        rank = {i: key(i) + 1e-9 * i for i in range(n)}
        g = _greedy_rank(inst, rank)
        if g is not None:
            s, m, c = g
            if c < best and check_schedule(inst, c, s, m):
                best, bs, bm = c, s, m
    return best, bs, bm


def pso_ub(inst, ub, s, m, npart, iters, seed=7):
    sw = Swarm(inst, ub, s, m, n_particles=npart, iters=iters,
               seed=seed, stall=4)
    best, st = sw.run()
    c, s2, m2 = best
    if c < ub and check_schedule(inst, c, s2, m2):
        return c, s2, m2, st
    return ub, s, m, st


def main():
    rows = []
    t_all = time.time()
    for corpus, name, idx, inst, known in corpora():
        lb, ub, s, m, est, q = base_bounds(inst)
        row = dict(corpus=corpus, name=name, idx=idx, known=known,
                   lb0=lb, ub0=ub)
        t = time.time()
        u, s2, m2 = portfolio(inst, ub, s, m)
        row['portfolio'] = u
        row['t_portfolio'] = time.time() - t
        for tag, npart, iters in (('pso8x12', 8, 12),
                                  ('pso8x24', 8, 24)):
            t = time.time()
            u, s2, m2, st = pso_ub(inst, ub, s, m, npart, iters)
            row[tag] = u
            row['t_' + tag] = time.time() - t
            row[tag + '_evals'] = st['evals']
        t = time.time()
        u, s2, m2, st = lns_drop(inst, ub, s, m, budget=40, kmax=14,
                                 tlim=0.4, seed=0, stall=8)
        row['lns'] = u
        row['t_lns'] = time.time() - t
        t = time.time()
        got, st = ga_schedule(inst, ub, pop=40, gens=60, budget=4000,
                              seed=0)
        if got is None:
            u = ub
        else:
            s2, m2 = got
            u = max(s2[i] + inst['p'][i] for i in range(inst['n']))
        row['ga'] = u
        row['t_ga'] = time.time() - t
        rows.append(row)
    out = dict(n=len(rows), rows=rows, summary={})
    for tag in ('ub0', 'portfolio', 'pso8x12', 'pso8x24', 'lns', 'ga'):
        gaps = collections.Counter(r[tag] - r['known'] for r in rows)
        out['summary'][tag] = dict(
            mean_u=round(sum(r[tag] for r in rows) / len(rows), 4),
            mean_gap=round(sum(r[tag] - r['known'] for r in rows) /
                           len(rows), 4),
            opt=sum(1 for r in rows if r[tag] == r['known']),
            gap_hist={str(k): v for k, v in sorted(gaps.items())},
            time=round(sum(r.get('t_' + tag, 0.0) for r in rows), 3))
    with open('exp/v91/bench_primal.json', 'w') as f:
        json.dump(out, f, indent=1)
    for tag, s in out['summary'].items():
        print(tag, s)
    print('wall', round(time.time() - t_all, 2))


if __name__ == '__main__':
    main()
