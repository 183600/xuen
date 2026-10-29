"""Live multi-leaf frontier with alpha cutoff on the 29 gap cases.

Each pre-split creates two boxes that partition the parent on a job's
start-time domain.  Children inherit the parent lower bound and proof;
a child is closed by alpha cutoff when L_f >= U.  The final object is a
v9.0 FrontierProof at U-1, audited leaf by leaf.
"""
import sys
import json
import time

sys.path[:0] = ['exp/v9mec', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from mec import run_frontier


def main():
    cases = json.load(open('exp/v10c/gap_cases.json'))
    rows = []
    for d in cases:
        for sp in (0, 1, 2, 3):
            for p in ('upper-first', 'binary'):
                r = run_frontier(d['inst'], d['opt'], d['case'],
                                 d.get('idx'), split_rounds=sp,
                                 policy=p)
                r['case'] = d['case']
                r['src'] = d['src']
                r['kind'] = d['kind']
                r['split_rounds'] = sp
                rows.append(r)
        print(d['case'], flush=True)
    json.dump(rows, open('exp/v9mec/bench_frontier.json', 'w'), indent=1)
    for p in ('upper-first', 'binary'):
        for sp in (0, 1, 2, 3):
            rs = [r for r in rows if r['policy'] == p and
                  r['split_rounds'] == sp]
            print('\n==', p, 'split_rounds', sp)
            print('ok', sum(r['ok'] for r in rs), '/', len(rs),
                  'cert', sum(r['certified'] for r in rs),
                  'frontier_ok', sum(r['frontier_ok'] for r in rs))
            print('leaves', sum(r['leaves'] for r in rs),
                  'splits', sum(r['splits'] for r in rs),
                  'prunes', sum(r['prunes'] for r in rs),
                  'probes', sum(r['probes'] for r in rs),
                  'searchLP', sum(r['pact_lp'] for r in rs),
                  'certLP', sum(r['pact_cert_lp'] for r in rs),
                  'totalLP', sum(r['pact_lp'] + r['pact_cert_lp']
                                 for r in rs),
                  't', round(sum(r['t'] for r in rs), 2))


if __name__ == '__main__':
    main()
