"""Benchmark v9.0 LSPACT on the 252-instance corpus."""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v8s', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from chip import base_corpus, pert_corpus, stress_corpus
from lspact import run_lspact


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
        r = run_lspact(inst, known, name, idx, **kw)
        r['corpus'] = corpus
        rows.append(r)
    wall = round(time.time() - t0, 2)
    with open('exp/v8s/bench_lspact_%s.json' % tag, 'w') as f:
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
              'ls_calls', sum(r['ls_calls'] for r in rs),
              'ls_yes', sum(r['ls_yes'] for r in rs),
              'ls_iters', sum(r['ls_iters'] for r in rs),
              'total', sum(r['total_audit'] for r in rs),
              't', round(sum(r['t'] for r in rs), 2))
    print('all ok', sum(r['ok'] for r in rows),
          'cert', sum(r['certified'] for r in rows),
          'q', sum(r['queries'] for r in rows),
          'pin', sum(r['pin_lp'] for r in rows),
          'pact_lp', sum(r['pact_lp'] for r in rows),
          'pact_nodes', sum(r['pact_nodes'] for r in rows),
          'ls_calls', sum(r['ls_calls'] for r in rows),
          'ls_yes', sum(r['ls_yes'] for r in rows),
          'ls_iters', sum(r['ls_iters'] for r in rows),
          'total', sum(r['total_audit'] for r in rows),
          't', round(sum(r['t'] for r in rows), 2))
    print('kinds', dict(collections.Counter(
        r['proof_kind'] for r in rows)))
    print('engines', {k: sum(r['stats2'].get(k, 0) for r in rows)
                      for k in ('pact_no', 'pact_yes', 'pact_unknown',
                                'ls_calls', 'ls_yes', 'ls_no',
                                'complete_fallback', 'chd_fallback')})
    return rows


if __name__ == '__main__':
    run_all('budget200', ls_budget=200, ls_restarts=1)
    run_all('budget400', ls_budget=400, ls_restarts=1)
    run_all('budget100', ls_budget=100, ls_restarts=1)
    run_all('off', ls_on=False)
