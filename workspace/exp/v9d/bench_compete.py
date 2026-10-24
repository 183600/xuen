"""v9.0 competitive-ratio curves for the constructor proposals.

At h=OPT we compare, under the same number of cheap greedy evaluations,
i.i.d. draws from the LP marginal against the Metropolis chain.  The
reported ratio is best greedy makespan / OPT at 50, 200, 1200 steps.
"""
import sys
import pickle
import time
import json
import random
import statistics

sys.path[:0] = ['exp/v9d', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

import numpy as np

from cab import CAB, _greedy_rank
from qnc import Budget

FILES = {'holdout': 'exp/v20/holdout_cases50.pkl',
         'synth': 'exp/v28/synth2_45.pkl',
         'large_a': 'exp/v14/large_a.pkl',
         'large_b': 'exp/v14/large_b.pkl',
         'large_het': 'exp/v14/large_het.pkl',
         'hard3': 'exp/v13/hard3.pkl',
         'deep': 'exp/v18/deep.pkl'}


def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt'])
            for x in d]


def corpus():
    return [(name, idx, inst, opt)
            for name, f in FILES.items()
            for idx, (inst, opt) in enumerate(load(f))]


def root_z(q):
    q.budget = 12
    q.nodecap = 200
    try:
        q._search([(0, 1)] * q.lp.base.N, 0)
    except Budget:
        pass
    if q.root_z is None:
        res = q.lp.solve([(0, 1)] * q.lp.base.N)
        q.lp_solves += 1
        if res.status == 0:
            q.root_z = np.array(res.x, copy=True)
    return q.root_z


def main():
    data = corpus()
    rows = []
    t0 = time.time()
    for ci, (name, idx, inst, opt) in enumerate(data):
        q = CAB(inst, opt, yes_scan=True)
        z = root_z(q)
        if z is None:
            continue
        q.cand_pool = []
        best = None
        marks = {}
        done = 0
        for k in [50, 200, 1200]:
            arch = q._mc_chain(z, k - done, 4000)
            done = k
            best = min(x[0] for x in arch)
            marks['mc%d' % k] = best
        dist = q._lp_distribution(z)
        rng = random.Random(999 + ci)
        best = 10 ** 9
        for s in range(1200):
            rank = q._sample_priority(dist, rng, q._domains(), 0.0)
            g = _greedy_rank(inst, rank)
            if g is not None and g[2] < best:
                best = g[2]
            if s + 1 in (50, 200, 1200):
                marks['iid%d' % (s + 1)] = best
        rows.append(dict(name=name, idx=idx, opt=opt, **marks))
    out = []
    for tag in ['mc50', 'mc200', 'mc1200', 'iid50', 'iid200', 'iid1200']:
        rs = [r[tag] / r['opt'] for r in rows]
        rec = dict(metric=tag, mean=round(sum(rs) / len(rs), 4),
                   median=round(statistics.median(rs), 4),
                   max=round(max(rs), 4),
                   hit=sum(r[tag] <= r['opt'] for r in rows),
                   n=len(rows))
        out.append(rec)
        print(rec)
    json.dump(dict(rows=rows, agg=out),
              open('exp/v9d/bench_compete.json', 'w'))
    print('time', round(time.time() - t0, 2))


if __name__ == '__main__':
    main()
