"""Benchmark TRIP-ICF (live frontier + core cut-lift) on normal/weak suites.

Baselines (capped one-leaf ICF and live frontier without cuts) are read
from the existing bench_budget_*.json files produced by the same
initializers and oracle.  This script writes exp/v8u/bench_trip_<suite>.json.
"""
import argparse
import json
import sys
import time

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from icf import corpora
from hap import weak_rows
from trip import run_trip


def items(which):
    if which == 'normal':
        return [(c, name, idx, inst, known, None)
                for c, name, idx, inst, known in corpora()]
    if which == 'weak':
        return [(c, name, idx, inst, known, initial)
                for c, name, idx, inst, known, initial
                in weak_rows(4)]
    raise ValueError(which)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--suite', choices=('normal', 'weak', 'both'),
                    default='normal')
    ap.add_argument('--B', type=int, default=1)
    ap.add_argument('--cut-q', type=int, default=2)
    ap.add_argument('--max-probes', type=int, default=200000)
    ap.add_argument('--timelimit', type=float, default=None)
    ap.add_argument('--no-audit', action='store_true')
    ap.add_argument('--limit', type=int, default=0)
    args = ap.parse_args()
    suites = ('normal', 'weak') if args.suite == 'both' else (args.suite,)
    for which in suites:
        rows = []
        t0 = time.time()
        its = items(which)
        if args.limit:
            its = its[:args.limit]
        for j, (c, name, idx, inst, known, initial) in enumerate(its):
            r = run_trip(inst, known, name, idx, B=args.B,
                         initial=initial, cut_q=args.cut_q,
                         max_probes=args.max_probes,
                         audit_every=not args.no_audit,
                         timelimit=args.timelimit)
            r['corpus'] = c
            rows.append(r)
            if (j + 1) % 10 == 0 or j + 1 == len(its):
                print('%s %d/%d %s t=%.1f' % (which, j + 1, len(its),
                                              name, time.time() - t0),
                      flush=True)
                with open('exp/v8u/bench_trip_%s.json' % which, 'w') as f:
                    json.dump(rows, f, indent=1)
        path = 'exp/v8u/bench_trip_%s.json' % which
        print('\n==', which, '->', path)
        for c in ('base', 'pert', 'stress'):
            rs = [r for r in rows if r['corpus'] == c]
            if not rs:
                continue
            print(c, 'n', len(rs),
                  'cert', sum(r['certified'] for r in rs),
                  'ok', sum(r['ok'] for r in rs),
                  'probes', sum(r['probes'] for r in rs),
                  'splits', sum(r['splits'] for r in rs),
                  'lp', sum(r['lp'] for r in rs),
                  'cut_lp', sum(r['cut_lp'] for r in rs),
                  'cut_ok', sum(r['cut_ok'] for r in rs),
                  'maxleaves', max(r['max_leaves'] for r in rs),
                  'pfail', sum(r['partial_fail'] for r in rs),
                  'rankfail', sum(r['rank_fail'] for r in rs),
                  't', round(sum(r['t'] for r in rs), 2))
        print('all n', len(rows),
              'cert', sum(r['certified'] for r in rows),
              'ok', sum(r['ok'] for r in rows),
              'probes', sum(r['probes'] for r in rows),
              'splits', sum(r['splits'] for r in rows),
              'lp', sum(r['lp'] for r in rows),
              'cut_lp', sum(r['cut_lp'] for r in rows),
              'cut_ok', sum(r['cut_ok'] for r in rows),
              'maxleaves', max(r['max_leaves'] for r in rows),
              'pfail', sum(r['partial_fail'] for r in rows),
              'rankfail', sum(r['rank_fail'] for r in rows),
              't', round(sum(r['t'] for r in rows), 2))


if __name__ == '__main__':
    main()
