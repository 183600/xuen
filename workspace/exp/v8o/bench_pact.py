"""Benchmark v8.9 PACT-ALC and its ablations on the 252-instance corpus."""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f', 'exp/v8e',
                'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from chip import base_corpus, pert_corpus, stress_corpus
from pact import run_pact


def corpora():
    for tag, rows in (('base', base_corpus()),
                      ('pert', pert_corpus()),
                      ('stress', stress_corpus())):
        for row in rows:
            if len(row) == 4:
                name, idx, inst, known = row
            else:
                idx, known, inst = row
                name = tag
            yield tag, name, idx, inst, known


def run_all(tag, **kw):
    rows = []
    t0 = time.time()
    for corpus, name, idx, inst, known in corpora():
        r = run_pact(inst, known, name, idx, **kw)
        r['corpus'] = corpus
        rows.append(r)
    wall = round(time.time() - t0, 2)
    with open('/tmp/pact_%s.json' % tag, 'w') as f:
        json.dump(rows, f, indent=1)
    with open('exp/v8o/bench_pact_%s.json' % tag, 'w') as f:
        json.dump(rows, f, indent=1)
    print('\n==', tag, '== wall', wall)
    for c in ('base', 'pert', 'stress'):
        rs = [r for r in rows if r['corpus'] == c]
        print(c, 'n', len(rs), 'ok', sum(r['ok'] for r in rs),
              'cert', sum(r['certified'] for r in rs),
              'q', sum(r['queries'] for r in rs),
              'pin', sum(r['pin_lp'] for r in rs),
              'pact_lp', sum(r['pact_lp'] for r in rs),
              'pact_nodes', sum(r['pact_nodes'] for r in rs),
              'pact_calls', sum(r['pact_calls'] for r in rs),
              'total', sum(r['total_audit'] for r in rs),
              't', round(sum(r['t'] for r in rs), 2))
    print('all ok', sum(r['ok'] for r in rows),
          'cert', sum(r['certified'] for r in rows),
          'q', sum(r['queries'] for r in rows),
          'pin', sum(r['pin_lp'] for r in rows),
          'pact_lp', sum(r['pact_lp'] for r in rows),
          'pact_nodes', sum(r['pact_nodes'] for r in rows),
          'pact_calls', sum(r['pact_calls'] for r in rows),
          'total', sum(r['total_audit'] for r in rows),
          't', round(sum(r['t'] for r in rows), 2))
    print('kinds', dict(collections.Counter(
        r['proof_kind'] for r in rows)))
    print('engines', {k: sum(r['stats2'].get(k, 0) for r in rows)
                      for k in ('pact_no', 'pact_yes', 'pact_unknown',
                                'ga_yes', 'ga_no', 'chd_fallback',
                                'complete_fallback')})
    return rows


if __name__ == '__main__':
    run_all('full', pact_depth=3)
    run_all('d1', pact_depth=1)
    run_all('d0', pact_depth=0)
    run_all('no_complete', pact_depth=3, complete_fallback=False)
    run_all('no_ga', pact_depth=3, use_ga=False)
    run_all('complete', pact_depth=None, use_ga=False)
    run_all('single3', pact_depth=3, pact_iterative=False)
    run_all('single1', pact_depth=1, pact_iterative=False)
    run_all('closing', pact_mode='closing')
