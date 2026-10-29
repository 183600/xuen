"""Regression run of CABS on the 252-instance main corpus.

The prior and cost model for each instance are fitted on the other 251
profile rows.  The gap distribution is degenerate (148 gaps of 0, 103
of 1, one of 5), so the leave-one-out prior is concentrated at d=0 and
CABS reduces to the lower-first / linear ladder.  The run checks that
the certificate layer still audits 252/252.
"""
import json
import sys
import time

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

import cabs
from icf import corpora
from pact import PACT, pact_decide


def main():
    profile = json.load(open('exp/v8u/cabs_profile_main.json'))
    rows = list(corpora())
    assert len(profile) == len(rows)
    cache = cabs.ProbeCache()
    out = {}
    t0 = time.time()
    for i, (corp, name, idx, inst, known) in enumerate(rows):
        co = PACT(inst, pact_mode='complete', use_ga=False)
        L, U, s, m = co.initial_bounds()
        pi = co._ensure_lb_proof(int(L))
        if pi is None:
            r = pact_decide(inst, int(L) - 1, depthcap=None, nodecap=None)
            if r['verdict'] is False:
                pi = r['proof']
        init = (int(L), int(U), list(s), list(m), pi)
        assert (init[0], init[1]) == (profile[i]['L'], profile[i]['U'])
        train = [p for j, p in enumerate(profile) if j != i]
        table = cabs.fit_prior(train, eps=0.5, shrinkage=5.0)
        cN, a, b = cabs.fit_cost(train)
        w = cabs.prior_weights(table, init[1] - init[0])
        for polname in ('cabs-1', 'lower-first', 'linear', 'binary'):
            pol = (cabs.Policy(polname, weights=w, cN=cN, a=a, b=b)
                   if polname == 'cabs-1' else cabs.Policy(polname))
            r = cabs.run_case(inst, known, init, pol, cache)
            r['corpus'] = corp
            r['name'] = name
            r['idx'] = idx
            out.setdefault(polname, []).append(r)
        if i % 50 == 0:
            print(i, corp, name, idx, 'cache', cache.misses, cache.hits,
                  'elapsed', round(time.time() - t0, 1), flush=True)
    with open('exp/v8u/bench_cabs_main.json', 'w') as f:
        json.dump(out, f, indent=1)
    print('wall', round(time.time() - t0, 2))
    for p, rs in out.items():
        print(p, 'ok', sum(r['ok'] for r in rs),
              'cert', sum(r['certified'] for r in rs),
              'probes', sum(r['probes'] for r in rs),
              'lp', sum(r['pact_lp'] for r in rs),
              'cert_lp', sum(r['pact_cert_lp'] for r in rs),
              'total', sum(r['pact_lp'] + r['pact_cert_lp'] for r in rs),
              'partial_fail', sum(r['partial_fail'] for r in rs),
              't', round(sum(r['t'] for r in rs), 2))


if __name__ == '__main__':
    main()
