"""Benchmark SCOPE-ALC (LP-rounding filter) against PACT-C on 252 cases."""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v9u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from chip import base_corpus, pert_corpus, stress_corpus
from pact import run_pact
from scope import run_scope


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


def run_all(tag, runner, **kw):
    rows = []
    t0 = time.time()
    for corpus, name, idx, inst, known in corpora():
        r = runner(inst, known, name, idx, **kw)
        r['corpus'] = corpus
        rows.append(r)
    wall = round(time.time() - t0, 2)
    with open('exp/v9u/bench_scope_%s.json' % tag, 'w') as f:
        json.dump(rows, f, indent=1)
    print('\n==', tag, '== wall', wall)
    for c in ('base', 'pert', 'stress'):
        rs = [r for r in rows if r['corpus'] == c]
        print(c, 'n', len(rs), 'ok', sum(r['ok'] for r in rs),
              'cert', sum(r['certified'] for r in rs),
              'q', sum(r['queries'] for r in rs),
              'pin', sum(r['pin_lp'] for r in rs),
              'pact_lp', sum(r['pact_lp'] for r in rs),
              'pact_cert', sum(r['pact_cert_lp'] for r in rs),
              'round_lp', sum(r.get('round_lp', 0) for r in rs),
              'round_yes', sum(r.get('round_yes', 0) for r in rs),
              'nodes', sum(r['pact_nodes'] for r in rs),
              'total', sum(r['total_audit'] for r in rs),
              't', round(sum(r['t'] for r in rs), 2))
    print('all ok', sum(r['ok'] for r in rows),
          'cert', sum(r['certified'] for r in rows),
          'q', sum(r['queries'] for r in rows),
          'pin', sum(r['pin_lp'] for r in rows),
          'pact_lp', sum(r['pact_lp'] for r in rows),
          'pact_cert', sum(r['pact_cert_lp'] for r in rows),
          'round_lp', sum(r.get('round_lp', 0) for r in rows),
          'round_yes', sum(r.get('round_yes', 0) for r in rows),
          'nodes', sum(r['pact_nodes'] for r in rows),
          'total', sum(r['total_audit'] for r in rows),
          't', round(sum(r['t'] for r in rows), 2))
    print('kinds', dict(collections.Counter(r['proof_kind'] for r in rows)))
    return rows


if __name__ == '__main__':
    run_all('pact_c', run_pact, pact_depth=None, use_ga=False)
    run_all('scope_c', run_scope, scope_mode='complete', scope_budget=3,
            pact_depth=None, use_ga=False)
    run_all('scope_c1', run_scope, scope_mode='complete', scope_budget=1,
            pact_depth=None, use_ga=False)
    run_all('scope_c2', run_scope, scope_mode='complete', scope_budget=2,
            pact_depth=None, use_ga=False)
