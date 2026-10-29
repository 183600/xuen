"""Benchmark v9.0 AIDA-ALC and its proof-space ablations."""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v9a', 'exp/v8j', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from chip import base_corpus, pert_corpus, stress_corpus
from aida import AIDA, DEFAULT_POLICIES, run


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
        r = run(AIDA, inst, known, name, idx, **kw)
        r['corpus'] = corpus
        rows.append(r)
    wall = round(time.time() - t0, 2)
    with open('/tmp/aida_%s.json' % tag, 'w') as f:
        json.dump(rows, f, indent=1)
    with open('exp/v9a/bench_aida_%s.json' % tag, 'w') as f:
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
    print('aida nodes', sum(sum(x['nodes'] for x in r['aida'])
                            for r in rows),
          'leaves', sum(sum(x['leaves'] for x in r['aida'])
                        for r in rows),
          'memo', sum(sum(x['memo_hits'] for x in r['aida'])
                      for r in rows),
          'sub', sum(sum(x['sub_hits'] for x in r['aida'])
                     for r in rows),
          'dag', sum(sum(x['dag_nodes'] for x in r['aida'])
                     for r in rows),
          'pol', sum(sum(x['policies_used'] for x in r['aida'])
                     for r in rows),
          'spacehit', sum(sum(x['space_hit'] for x in r['aida'])
                          for r in rows))
    return rows


if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else 'full'
    if which == 'full':
        run_all('full')
    elif which == 'no_memo':
        run_all('no_memo', aida_use_memo=False)
    elif which == 'no_sub':
        run_all('no_sub', aida_use_sub=False)
    elif which == 'no_memo_sub':
        run_all('no_memo_sub', aida_use_memo=False, aida_use_sub=False)
    elif which == 'single':
        run_all('single', aida_policies=[DEFAULT_POLICIES[0]])
    elif which == 'closure':
        run_all('closure', aida_closure=True)
    elif which == 'space128':
        run_all('space128', aida_spacecap=128)
    elif which == 'space256':
        run_all('space256', aida_spacecap=256)
    elif which == 'all':
        run_all('full')
        run_all('no_memo', aida_use_memo=False)
        run_all('no_sub', aida_use_sub=False)
        run_all('no_memo_sub', aida_use_memo=False, aida_use_sub=False)
        run_all('single', aida_policies=[DEFAULT_POLICIES[0]])
        run_all('closure', aida_closure=True)
        run_all('space128', aida_spacecap=128)
        run_all('space256', aida_spacecap=256)
    else:
        raise SystemExit('unknown: %s' % which)
