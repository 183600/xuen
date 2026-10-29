"""Compare probe policies on the 29 large-gap cases (OPT near U)."""
import sys
import json
import time

sys.path[:0] = ['exp/v9mec', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from mec import run_mec, worst_case_probes


def main():
    cases = json.load(open('exp/v10c/gap_cases.json'))
    policies = ['lower-first', 'binary', 'upper-first', 'pact', 'minimax']
    rows = []
    for d in cases:
        for p in policies:
            r = run_mec(d['inst'], d['opt'], d['case'], d.get('idx'),
                        policy=p)
            r['case'] = d['case']
            r['src'] = d['src']
            r['kind'] = d['kind']
            rows.append(r)
        print(d['case'], 'gap', d['ub0'] - d['lb0'], flush=True)
    json.dump(rows, open('exp/v9mec/bench_gap.json', 'w'), indent=1)
    for p in policies:
        rs = [r for r in rows if r['policy'] == p]
        print('\n==', p)
        print('ok', sum(r['ok'] for r in rs), '/', len(rs),
              'cert', sum(r['certified'] for r in rs),
              'partial_fail', sum(r['partial_fail'] for r in rs))
        print('probes', sum(r['probes'] for r in rs),
              'searchLP', sum(r['pact_lp'] for r in rs),
              'certLP', sum(r['pact_cert_lp'] for r in rs),
              'totalLP', sum(r['pact_lp'] + r['pact_cert_lp'] for r in rs),
              't', round(sum(r['t'] for r in rs), 2))
        by = {}
        for r in rs:
            by.setdefault(r['gap0'], []).append(r)
        for g in sorted(by):
            xs = by[g]
            print('  gap', g, 'n', len(xs),
                  'q', sum(r['probes'] for r in xs),
                  'lp', sum(r['pact_lp'] + r['pact_cert_lp'] for r in xs))


if __name__ == '__main__':
    main()
