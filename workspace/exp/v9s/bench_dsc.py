"""Benchmark v9.0 DSC-ALC on the 252-instance corpus."""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v9s', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from chip import base_corpus, pert_corpus, stress_corpus
from dsc import run_dsc


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
        r = run_dsc(inst, known, name, idx, **kw)
        r['corpus'] = corpus
        rows.append(r)
    wall = round(time.time() - t0, 2)
    with open('exp/v9s/bench_dsc_%s.json' % tag, 'w') as f:
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
              'sample_lp', sum(r.get('sample_lp', 0) for r in rs),
              'sample_hits', sum(r.get('sample_hits', 0) for r in rs),
              'sample_miss', sum(r.get('sample_misses', 0) for r in rs),
              'total', sum(r['total_audit'] for r in rs),
              't', round(sum(r['t'] for r in rs), 2))
    print('all ok', sum(r['ok'] for r in rows),
          'cert', sum(r['certified'] for r in rows),
          'q', sum(r['queries'] for r in rows),
          'pact_lp', sum(r['pact_lp'] for r in rows),
          'pact_nodes', sum(r['pact_nodes'] for r in rows),
          'sample_lp', sum(r.get('sample_lp', 0) for r in rows),
          'sample_hits', sum(r.get('sample_hits', 0) for r in rows),
          'sample_miss', sum(r.get('sample_misses', 0) for r in rows),
          'sample_calls', sum(r.get('sample_calls', 0) for r in rows),
          'total', sum(r['total_audit'] for r in rows),
          't', round(sum(r['t'] for r in rows), 2))
    print('kinds', dict(collections.Counter(
        r['proof_kind'] for r in rows)))
    return rows


if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else 'b64'
    kw = dict(sample_budget=64)
    if which == 'b256':
        kw = dict(sample_budget=256)
    elif which == 'b16':
        kw = dict(sample_budget=16)
    elif which == 'b32':
        kw = dict(sample_budget=32)
    elif which == 'b128':
        kw = dict(sample_budget=128)
    elif which == 'b1024':
        kw = dict(sample_budget=1024)
    elif which == 'b0':
        kw = dict(sample_budget=0, sample_first=False)
    elif which == 'uniform':
        kw = dict(sample_budget=64, sample_mode='uniform')
    elif which == 'random':
        kw = dict(sample_budget=64, sample_mode='random')
    elif which == 'nodiv':
        kw = dict(sample_budget=64, diversify=False)
    elif which == 'usrc':
        kw = dict(sample_budget=128, sample_source='uniform')
    elif which == 'rnd':
        kw = dict(sample_budget=128, sample_mode='random')
    run_all(which, **kw)
