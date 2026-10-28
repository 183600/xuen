"""Ablation of the CABS prior shrinkage on the 160-instance weak corpus.

All runs share one ProbeCache, so the LP counts are the quantities that
matter; wall time is not comparable across rows.
"""
import json
import sys
import time

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

import cabs
from hap import weak_rows


def main():
    profile = json.load(open('exp/v8u/cabs_profile.json'))
    rows = weak_rows(4)
    cache = cabs.ProbeCache()
    out = {}
    t0 = time.time()
    for shrink in (0.0, 1.0, 5.0, 10.0):
        for name, cap in (('cabs-1', None), ('cabs-guard', 0.5)):
            rs = []
            for i, (corp, nm, idx, inst, known, init) in enumerate(rows):
                train = [p for j, p in enumerate(profile) if j != i]
                table = cabs.fit_prior(train, eps=0.5, shrinkage=shrink)
                cN, a, b = cabs.fit_cost(train)
                w = cabs.prior_weights(table, init[1] - init[0])
                pol = cabs.Policy(name, weights=w, cN=cN, a=a, b=b,
                                  yes_cap=cap)
                r = cabs.run_case(inst, known, init, pol, cache)
                r['corpus'] = corp
                r['name'] = nm
                r['idx'] = idx
                rs.append(r)
            out['%s-shrink:%g' % (name, shrink)] = rs
            print(name, shrink, 'data', cache.misses, cache.hits,
                  'elapsed', round(time.time() - t0, 1), flush=True)
    for name in ('linear', 'binary', 'lower-first', 'pact'):
        rs = []
        for corp, nm, idx, inst, known, init in rows:
            pol = cabs.Policy(name)
            r = cabs.run_case(inst, known, init, pol, cache)
            r['corpus'] = corp
            r['name'] = nm
            r['idx'] = idx
            rs.append(r)
        out[name] = rs
    with open('exp/v8u/bench_cabs_ablate.json', 'w') as f:
        json.dump(out, f, indent=1)
    print('wall', round(time.time() - t0, 2))
    for k, rs in out.items():
        print(k,
              'ok', sum(r['ok'] for r in rs),
              'probes', sum(r['probes'] for r in rs),
              'lp', sum(r['pact_lp'] for r in rs),
              'cert', sum(r['pact_cert_lp'] for r in rs),
              'total', sum(r['pact_lp'] + r['pact_cert_lp'] for r in rs),
              'fail', sum(r['partial_fail'] for r in rs))


if __name__ == '__main__':
    main()
