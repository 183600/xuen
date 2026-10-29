"""Run PACT-W with width budgets 5 and 9 on the 252-instance corpus."""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v8p', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from chip import base_corpus, pert_corpus, stress_corpus
from pact_w import run_pact_w


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


def run_all(tag, B):
    rows = []
    t0 = time.time()
    for corpus, name, idx, inst, known in corpora():
        r = run_pact_w(inst, known, name, idx, width_budget=B)
        r['corpus'] = corpus
        rows.append(r)
    wall = round(time.time() - t0, 2)
    with open('exp/v8p/bench_w_%s.json' % tag, 'w') as f:
        json.dump(rows, f, indent=1)
    print('\n==', tag, 'B', B, '== wall', wall)
    for c in ('base', 'pert', 'stress'):
        rs = [r for r in rows if r['corpus'] == c]
        print(c, 'n', len(rs), 'ok', sum(r['ok'] for r in rs),
              'q', sum(r['queries'] for r in rs),
              'lp', sum(r['res_lp'] for r in rs),
              'cert', sum(r['res_cert_lp'] for r in rs),
              'resumed', sum(r['res_resumed'] for r in rs),
              't', round(sum(r['t'] for r in rs), 2))
    print('all ok', sum(r['ok'] for r in rows),
          'q', sum(r['queries'] for r in rows),
          'lp', sum(r['res_lp'] for r in rows),
          'cert', sum(r['res_cert_lp'] for r in rows),
          'resumed', sum(r['res_resumed'] for r in rows),
          'total', sum(r['total_audit'] for r in rows),
          't', round(sum(r['t'] for r in rows), 2))
    print('kinds', dict(collections.Counter(
        r['proof_kind'] for r in rows)))
    return rows


if __name__ == '__main__':
    run_all('b5', 5)
    run_all('b9', 9)
