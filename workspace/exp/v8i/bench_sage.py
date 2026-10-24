"""Benchmark v8.8 SAGE-ALC and its two engine ablations."""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v8i', 'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g',
                'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a',
                'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60',
                'exp/v13']

from chip import base_corpus, pert_corpus, stress_corpus
from sage import SAGE, run


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
        r = run(SAGE, inst, known, name, idx, **kw)
        r['corpus'] = corpus
        rows.append(r)
    wall = round(time.time() - t0, 2)
    with open('/tmp/sage_%s.json' % tag, 'w') as f:
        json.dump(rows, f, indent=1)
    with open('exp/v8i/bench_sage_%s.json' % tag, 'w') as f:
        json.dump(rows, f, indent=1)
    print('\n==', tag, '== wall', wall)
    for c in ('base', 'pert', 'stress'):
        rs = [r for r in rows if r['corpus'] == c]
        print(c, 'n', len(rs), 'ok', sum(r['ok'] for r in rs),
              'cert', sum(r['certified'] for r in rs),
              'q', sum(r['queries'] for r in rs),
              'lpchd', sum(r['lp'] for r in rs),
              'pin', sum(r['pin_lp'] for r in rs),
              'bb', sum(r['bb_lp'] for r in rs),
              'certlp', sum(r['cert_lp'] for r in rs),
              'yn', sum(r['yes_nodes'] for r in rs),
              't', round(sum(r['t'] for r in rs), 2))
    print('all ok', sum(r['ok'] for r in rows),
          'cert', sum(r['certified'] for r in rows),
          'q', sum(r['queries'] for r in rows),
          'lpchd', sum(r['lp'] for r in rows),
          'pin', sum(r['pin_lp'] for r in rows),
          'bb', sum(r['bb_lp'] for r in rows),
          'certlp', sum(r['cert_lp'] for r in rows),
          'yn', sum(r['yes_nodes'] for r in rows),
          't', round(sum(r['t'] for r in rows), 2))
    print('kinds', dict(collections.Counter(
        r['proof_kind'] for r in rows)))
    print('engines bb(y/n/u)',
          sum(r['stats2'].get('bb_yes', 0) for r in rows),
          sum(r['stats2'].get('bb_no', 0) for r in rows),
          sum(r['stats2'].get('bb_unknown', 0) for r in rows),
          'ga(y/n)',
          sum(r['stats2'].get('ga_yes', 0) for r in rows),
          sum(r['stats2'].get('ga_no', 0) for r in rows),
          'chd', sum(r['stats2'].get('chd_fallback', 0)
                     for r in rows))
    return rows


if __name__ == '__main__':
    run_all('full')
    run_all('no_ga', use_ga=False)
    run_all('no_bb', use_bb=False)
    run_all('bb_no_only', bb_yes=False)
