"""Fair A/B: KARST vs RACE on the 252-instance corpus, alternating order."""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v9r', 'exp/v9y', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from chip import base_corpus, pert_corpus, stress_corpus
from karst import run_karst
from race import run_race


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


def summarize(tag, rows):
    print('\n==', tag, '==')
    for c in ('base', 'pert', 'stress'):
        rs = [r for r in rows if r['corpus'] == c]
        print(c, 'n', len(rs), 'ok', sum(r['ok'] for r in rs),
              'cert', sum(r['certified'] for r in rs),
              'q', sum(r['queries'] for r in rs),
              'pact_lp', sum(r.get('pact_lp', 0) for r in rs),
              'nodes', sum(r.get('pact_nodes', 0) for r in rs),
              'trials', sum(r.get('karst_trials', 0) for r in rs),
              'capunk', sum(r.get('race_cap_unknown', 0) for r in rs),
              'total', sum(r['total_audit'] for r in rs),
              't', round(sum(r['t'] for r in rs), 2))
    print('all ok', sum(r['ok'] for r in rows),
          'cert', sum(r['certified'] for r in rows),
          'q', sum(r['queries'] for r in rows),
          'pact_lp', sum(r.get('pact_lp', 0) for r in rows),
          'nodes', sum(r.get('pact_nodes', 0) for r in rows),
          'trials', sum(r.get('karst_trials', 0) for r in rows),
          'capunk', sum(r.get('race_cap_unknown', 0) for r in rows),
          'total', sum(r['total_audit'] for r in rows),
          't', round(sum(r['t'] for r in rows), 2))
    print('kinds', dict(collections.Counter(r['proof_kind']
                                            for r in rows)))


def main(cap=5):
    out = {'karst': [], 'race': []}
    t0 = time.time()
    for corpus, name, idx, inst, known in corpora():
        # Alternate which engine goes first to cancel CPU drift.
        engines = [('karst', run_karst), ('race', run_race)]
        if len(out['karst']) % 2:
            engines.reverse()
        for tag, runner in engines:
            kw = {} if tag == 'karst' else {'race_caps': (cap,)}
            r = runner(inst, known, name, idx, **kw)
            r['corpus'] = corpus
            out[tag].append(r)
    wall = round(time.time() - t0, 2)
    for tag in ('karst', 'race'):
        summarize(tag, out[tag])
    with open('exp/v9r/bench_ab_cap%d.json' % cap, 'w') as f:
        json.dump(out, f, indent=1)
    print('\nwall', wall)
    # paired totals
    for tag in ('karst', 'race'):
        print(tag, 'sum t', round(sum(r['t'] for r in out[tag]), 3))
    return out


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
