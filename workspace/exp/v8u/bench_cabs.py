"""Benchmark CABS on the 160-instance weak corpus with live certificates.

The weak initial bounds come from hap.weak_rows(4).  The prior and cost
model for each test instance are fitted on the other 159 profile rows
(leave-one-out), so the test instance's OPT is never used to choose a
probe.  All policies share one ProbeCache; the cache only removes
repeated LP solves, it does not change any verdict or cost.
"""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

import cabs
from hap import weak_rows


def main():
    profile = json.load(open('exp/v8u/cabs_profile.json'))
    rows = weak_rows(4)
    assert len(profile) == len(rows)
    for i, ((c, name, idx, inst, known, init), p) in enumerate(zip(rows, profile)):
        assert (p['corpus'], p['name'], p['idx'], p['known'],
                p['L'], p['U'], p['n'], p['m']) == \
               (c, name, idx, known, init[0], init[1], inst['n'], inst['m']), i

    cache = cabs.ProbeCache()
    names = ('linear', 'binary', 'lower-first', 'pact',
             'cabs-1', 'cabs-dp', 'cabs-guard')
    out = {n: [] for n in names}
    t0 = time.time()
    for i, (corp, name, idx, inst, known, init) in enumerate(rows):
        train = [p for j, p in enumerate(profile) if j != i]
        table = cabs.fit_prior(train, eps=0.5, shrinkage=5.0)
        cN, a, b = cabs.fit_cost(train)
        g = init[1] - init[0]
        w = cabs.prior_weights(table, g)
        for pol in names:
            if pol.startswith('cabs'):
                policy = cabs.Policy(pol, weights=w, cN=cN, a=a, b=b,
                                     yes_cap=(0.5 if pol == 'cabs-guard'
                                              else None))
            else:
                policy = cabs.Policy(pol)
            r = cabs.run_case(inst, known, init, policy, cache)
            r['corpus'] = corp
            r['name'] = name
            r['idx'] = idx
            out[pol].append(r)
        if i % 20 == 0:
            print(i, corp, name, idx, 'cache', cache.misses, cache.hits,
                  'elapsed', round(time.time() - t0, 1), flush=True)

    with open('exp/v8u/bench_cabs_weak.json', 'w') as f:
        json.dump(out, f, indent=1)
    print('\nwall', round(time.time() - t0, 2), 'cache',
          cache.misses, 'misses', cache.hits, 'hits')
    for pol in names:
        rs = out[pol]
        print(pol,
              'ok', sum(r['ok'] for r in rs),
              'cert', sum(r['certified'] for r in rs),
              'probes', sum(r['probes'] for r in rs),
              'lp', sum(r['pact_lp'] for r in rs),
              'cert_lp', sum(r['pact_cert_lp'] for r in rs),
              'total', sum(r['pact_lp'] + r['pact_cert_lp'] for r in rs),
              'partial_fail', sum(r['partial_fail'] for r in rs),
              't', round(sum(r['t'] for r in rs), 2))


if __name__ == '__main__':
    main()
