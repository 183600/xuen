"""Run AEGIS-PACT (synthesized theta) on the 252-instance corpus."""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v10c', 'exp/v10b', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from aegis import run_aegis, SEARCH_FEATURES
from icf import corpora


def load_theta():
    d = json.load(open('exp/v10c/bench_aegis.json'))
    return d['selected_x']


def main():
    th = load_theta()
    print('theta', [round(v, 4) for v in th], flush=True)
    rows = []
    t0 = time.time()
    for corpus, name, idx, inst, known in corpora():
        r = run_aegis(inst, known, name, idx, theta=th,
                      policy='lower-first', max_probes=64,
                      use_static=True, fallback=True)
        r['corpus'] = corpus
        rows.append(r)
    wall = round(time.time() - t0, 2)
    with open('exp/v10c/bench_main.json', 'w') as f:
        json.dump(rows, f, indent=1)
    print('wall', wall)
    for c in ('base', 'pert', 'stress'):
        rs = [r for r in rows if r['corpus'] == c]
        print(c, 'n', len(rs), 'ok', sum(r['ok'] for r in rs),
              'cert', sum(r['certified'] for r in rs),
              'partial_fail', sum(r['partial_fail'] for r in rs),
              'q', sum(r['queries'] for r in rs),
              'lp', sum(r['pact_lp'] for r in rs),
              'cert_lp', sum(r['pact_cert_lp'] for r in rs),
              'pin', sum(r['pin_lp'] for r in rs),
              'static', sum(r['static_closed'] for r in rs),
              'fallback', sum(r['fallbacks'] for r in rs),
              't', round(sum(r['t'] for r in rs), 2))
    print('all ok', sum(r['ok'] for r in rows),
          'cert', sum(r['certified'] for r in rows),
          'partial_fail', sum(r['partial_fail'] for r in rows),
          'partial_checks', sum(r['partial_ok'] + r['partial_fail']
                                for r in rows),
          'q', sum(r['queries'] for r in rows),
          'lp', sum(r['pact_lp'] for r in rows),
          'cert_lp', sum(r['pact_cert_lp'] for r in rows),
          'pin', sum(r['pin_lp'] for r in rows),
          'static', sum(r['static_closed'] for r in rows),
          'fallback', sum(r['fallbacks'] for r in rows),
          't', round(sum(r['t'] for r in rows), 2))
    print('kinds', dict(collections.Counter(r['proof_kind'] for r in rows)))
    hist = collections.Counter()
    for r in rows:
        hist[(r['ub0'] - r['lb0'], r['queries'])] += 1
    print('(gap,q):', dict(sorted(hist.items())))


if __name__ == '__main__':
    main()
