"""Run MEC single-leaf policies on the 252-instance corpus."""
import sys
import json
import time

sys.path[:0] = ['exp/v9mec', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from icf import corpora
from mec import run_mec


def main():
    policies = ['lower-first', 'binary', 'upper-first', 'minimax']
    rows = []
    t0 = time.time()
    for k, (tag, name, idx, inst, known) in enumerate(corpora()):
        for p in policies:
            r = run_mec(inst, known, name, idx, policy=p)
            r['corpus'] = tag
            rows.append(r)
        if k % 20 == 0:
            print(k, round(time.time() - t0, 1), flush=True)
    json.dump(rows, open('exp/v9mec/bench_252.json', 'w'), indent=1)
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
        for g in sorted({r['gap0'] for r in rs}):
            xs = [r for r in rs if r['gap0'] == g]
            print('  gap', g, 'n', len(xs),
                  'q', sum(r['probes'] for r in xs),
                  'lp', sum(r['pact_lp'] + r['pact_cert_lp'] for r in xs))


if __name__ == '__main__':
    main()
