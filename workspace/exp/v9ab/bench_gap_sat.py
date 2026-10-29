"""Benchmark AB-SAT/ICF on the 29 gap cases.

--policy ab-sat      : SAT-shielded null window U-1
--policy upper-first : trusted null window U-1 without SAT
--policy lower-first : v9.0 lower-first (run_icf)
"""
import argparse
import json
import sys
import time

sys.path[:0] = ['exp/v9ab', 'exp/v8t', 'exp/v8u', 'exp/v8o',
                'exp/v8i', 'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g',
                'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a',
                'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60',
                'exp/v13']

from ab_sat import run_ab_sat
from icf import run_icf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--policy', default='ab-sat',
                    choices=('ab-sat', 'upper-first', 'lower-first'))
    ap.add_argument('--out', default=None)
    args = ap.parse_args()
    cases = json.load(open('exp/v10c/gap_cases.json'))
    rows = []
    t0 = time.time()
    for d in cases:
        name = d['case']
        if args.policy == 'ab-sat':
            r = run_ab_sat(d['inst'], d['opt'], name, d.get('idx'),
                           sat_enabled=True)
        elif args.policy == 'upper-first':
            r = run_ab_sat(d['inst'], d['opt'], name, d.get('idx'),
                           sat_enabled=False)
        else:
            r = run_icf(d['inst'], d['opt'], name, d.get('idx'),
                        policy='lower-first')
        r['case'] = name
        r['kind'] = d['kind']
        rows.append(r)
        print(name, 'ok', r.get('ok'), 'q', r.get('probes', r.get('queries')),
              'lp', r.get('pact_lp'), 'cert', r.get('pact_cert_lp'),
              'sat', r.get('sat_calls', 0), flush=True)
    out = args.out or ('exp/v9ab/bench_%s_gap.json' %
                       args.policy.replace('-', '_'))
    json.dump(rows, open(out, 'w'), indent=1)
    print('saved', out, 'wall', round(time.time() - t0, 2))
    print('sum q', sum(r.get('probes', r.get('queries', 0)) for r in rows),
          'lp', sum(r.get('pact_lp', 0) for r in rows),
          'cert', sum(r.get('pact_cert_lp', 0) for r in rows),
          'ok', sum(bool(r.get('ok')) for r in rows))


if __name__ == '__main__':
    main()
