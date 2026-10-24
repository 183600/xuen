"""Benchmark v8.7 APEX-ALC and its ablations on the three v8.1 corpora."""
import json
import sys

sys.path[:0] = ['exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g',
                'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a',
                'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60',
                'exp/v13']

from chip import base_corpus, pert_corpus, stress_corpus
from apex import APEX, run


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
    for corpus, name, idx, inst, known in corpora():
        r = run(APEX, inst, known, name, idx, **kw)
        r['corpus'] = corpus
        rows.append(r)
    with open('/tmp/apex_%s.json' % tag, 'w') as f:
        json.dump(rows, f, indent=1)
    with open('exp/v8h/bench_apex_%s.json' % tag, 'w') as f:
        json.dump(rows, f, indent=1)
    print('\n==', tag, '==')
    for c in ('base', 'pert', 'stress'):
        rs = [r for r in rows if r['corpus'] == c]
        print(c, 'n', len(rs), 'ok', sum(r['ok'] for r in rs),
              'cert', sum(r['certified'] for r in rs),
              'q', sum(r['queries'] for r in rs),
              'lp', sum(r['lp'] for r in rs),
              'yn', sum(r['yes_nodes'] for r in rs),
              't', round(sum(r['t'] for r in rs), 2))
    print('all q', sum(r['queries'] for r in rows),
          'lp', sum(r['lp'] for r in rows),
          'yn', sum(r['yes_nodes'] for r in rows),
          't', round(sum(r['t'] for r in rows), 2),
          'ok', sum(r['ok'] for r in rows))


if __name__ == '__main__':
    run_all('full')
    run_all('no_lns', use_lns=False)
    run_all('no_proof', use_proof=False)
    run_all('no_lp', use_lp=False, use_lp_sched=False)
