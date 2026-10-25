"""Benchmark RACE-ALC on the 252-instance corpus."""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v9r', 'exp/v9y', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from chip import base_corpus, pert_corpus, stress_corpus
from race import run_race
from karst import run_karst


def corpora():
    for tag, rows in (('base', base_corpus()), ('pert', pert_corpus()),
                      ('stress', stress_corpus())):
        for row in rows:
            if len(row) == 4:
                name, idx, inst, known = row
            else:
                idx, known, inst = row
                name = tag
            yield tag, name, idx, inst, known


def summarize(tag, rows, wall):
    print('\n==', tag, '== wall', wall)
    for c in ('base', 'pert', 'stress'):
        rs = [r for r in rows if r['corpus'] == c]
        print(c, 'n', len(rs), 'ok', sum(r['ok'] for r in rs),
              'cert', sum(r['certified'] for r in rs),
              'q', sum(r['queries'] for r in rs),
              'pin', sum(r['pin_lp'] for r in rs),
              'pact_lp', sum(r.get('pact_lp', 0) for r in rs),
              'race_lp', sum(r.get('race_lp', 0) for r in rs),
              'samples', sum(r.get('race_samples', 0) for r in rs),
              'capunk', sum(r.get('race_cap_unknown', 0) for r in rs),
              'symyes', sum(r.get('race_sample_yes', 0) for r in rs),
              'pyes', sum(r.get('race_pact_yes', 0) for r in rs),
              'pno', sum(r.get('race_pact_no', 0) for r in rs),
              'nodes', sum(r.get('pact_nodes', 0) for r in rs),
              'total', sum(r['total_audit'] for r in rs),
              't', round(sum(r['t'] for r in rs), 2))
    print('all ok', sum(r['ok'] for r in rows),
          'cert', sum(r['certified'] for r in rows),
          'q', sum(r['queries'] for r in rows),
          'pin', sum(r['pin_lp'] for r in rows),
          'pact_lp', sum(r.get('pact_lp', 0) for r in rows),
          'race_lp', sum(r.get('race_lp', 0) for r in rows),
          'samples', sum(r.get('race_samples', 0) for r in rows),
          'capunk', sum(r.get('race_cap_unknown', 0) for r in rows),
          'symyes', sum(r.get('race_sample_yes', 0) for r in rows),
          'pyes', sum(r.get('race_pact_yes', 0) for r in rows),
          'pno', sum(r.get('race_pact_no', 0) for r in rows),
          'nodes', sum(r.get('pact_nodes', 0) for r in rows),
          'total', sum(r['total_audit'] for r in rows),
          't', round(sum(r['t'] for r in rows), 2))
    print('kinds', dict(collections.Counter(r['proof_kind']
                                            for r in rows)))


def run_all(tag, runner, **kw):
    rows = []
    t0 = time.time()
    for corpus, name, idx, inst, known in corpora():
        r = runner(inst, known, name, idx, **kw)
        r['corpus'] = corpus
        rows.append(r)
    wall = round(time.time() - t0, 2)
    with open('exp/v9r/bench_%s.json' % tag, 'w') as f:
        json.dump(rows, f, indent=1)
    summarize(tag, rows, wall)
    return rows


if __name__ == '__main__':
    run_all('race', run_race)
