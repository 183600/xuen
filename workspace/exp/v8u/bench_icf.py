"""Benchmark ICF-PACT on the 252-instance corpus.

The one-leaf specialization is compared under four probe policies:
  pact         : PACT-C's scan<=4 then binary
  lower-first  : probe L once, then binary
  upper-first  : probe U-1
  binary       : no scan
"""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from icf import run_icf, corpora


POLICIES = ('pact', 'lower-first', 'upper-first', 'binary')


def run_policy(policy):
    rows = []
    t0 = time.time()
    for corpus, name, idx, inst, known in corpora():
        r = run_icf(inst, known, name, idx, policy=policy)
        r['corpus'] = corpus
        rows.append(r)
    wall = round(time.time() - t0, 2)
    path = 'exp/v8u/bench_icf_%s.json' % policy
    with open(path, 'w') as f:
        json.dump(rows, f, indent=1)
    print('\n==', policy, '== wall', wall)
    for c in ('base', 'pert', 'stress'):
        rs = [r for r in rows if r['corpus'] == c]
        print(c, 'n', len(rs), 'ok', sum(r['ok'] for r in rs),
              'cert', sum(r['certified'] for r in rs),
              'partial_fail', sum(r['partial_fail'] for r in rs),
              'q', sum(r['queries'] for r in rs),
              'lp', sum(r['pact_lp'] for r in rs),
              'pin', sum(r['pin_lp'] for r in rs),
              't', round(sum(r['t'] for r in rs), 2))
    print('all ok', sum(r['ok'] for r in rows),
          'cert', sum(r['certified'] for r in rows),
          'partial_fail', sum(r['partial_fail'] for r in rows),
          'partial_checks', sum(r['partial_ok'] + r['partial_fail']
                                for r in rows),
          'q', sum(r['queries'] for r in rows),
          'lp', sum(r['pact_lp'] for r in rows),
          'pin', sum(r['pin_lp'] for r in rows),
          't', round(sum(r['t'] for r in rows), 2))
    print('kinds', dict(collections.Counter(r['proof_kind'] for r in rows)))
    hist = collections.Counter()
    for r in rows:
        hist[(r['ub0'] - r['lb0'], r['queries'])] += 1
    print('(gap0,q):', dict(sorted(hist.items())))
    return rows


def compare(rows_by_policy):
    base = {(r['corpus'], r['name'], r['idx'], r['ub0'], r['lb0']): r
            for r in rows_by_policy['pact']}
    print('\n== per-instance deltas vs pact ==')
    for pol in ('lower-first', 'upper-first', 'binary'):
        dl = 0
        dt = 0.0
        better = same = worse = 0
        for r in rows_by_policy[pol]:
            key = (r['corpus'], r['name'], r['idx'], r['ub0'], r['lb0'])
            b = base[key]
            d = r['pact_lp'] - b['pact_lp']
            dl += d
            dt += r['t'] - b['t']
            if d < 0:
                better += 1
            elif d == 0:
                same += 1
            else:
                worse += 1
        print(pol, 'dlp', dl, 'dt', round(dt, 3),
              'better/same/worse', better, same, worse)


if __name__ == '__main__':
    out = {}
    for pol in POLICIES:
        out[pol] = run_policy(pol)
    compare(out)
