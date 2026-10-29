"""Benchmark LPR-ICF on the weak 160 and main 252 corpora.

Usage (from the workspace directory):
    .venv/bin/python exp/v8u/bench_lpr.py --which weak --mode rand
    .venv/bin/python exp/v8u/bench_lpr.py --which main --mode rand
    .venv/bin/python exp/v8u/bench_lpr.py --which weak --mode det
    .venv/bin/python exp/v8u/bench_lpr.py --which weak --mode none
"""
import argparse
import collections
import json
import sys
import time

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from lpr import run_lpr, weak_rows, main_rows


def rows_for(which):
    if which == 'weak':
        for c, name, idx, inst, known, initial in weak_rows(4):
            yield c, name, idx, inst, known, initial
    elif which == 'main':
        for c, name, idx, inst, known in main_rows():
            yield c, name, idx, inst, known, None
    else:
        raise ValueError(which)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--which', choices=['weak', 'main'], required=True)
    ap.add_argument('--mode', choices=['rand', 'det', 'none', 'fresh'],
                    default='rand')
    ap.add_argument('--pre', type=int, default=50)
    ap.add_argument('--post', type=int, default=200)
    ap.add_argument('--seed-offset', type=int, default=0)
    ap.add_argument('--time-cap', type=float, default=0.08)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    out = []
    t0 = time.time()
    for k, (c, name, idx, inst, known, initial) in enumerate(
            rows_for(args.which)):
        r = run_lpr(inst, known, name, idx, initial=initial,
                    mode=args.mode, pre_rand=args.pre,
                    post_rand=args.post, time_cap=args.time_cap,
                    seed=k + args.seed_offset)
        r['corpus'] = c
        out.append(r)
        if args.which == 'main' and k % 50 == 0:
            print('  ..', k, '/', 252, 't', round(time.time() - t0, 1))
    wall = round(time.time() - t0, 2)
    if args.out is None:
        args.out = 'exp/v8u/bench_lpr_%s_%s_s%d.json' % (
            args.which, args.mode, args.seed_offset)
    with open(args.out, 'w') as f:
        json.dump(out, f, indent=1)

    print('\n== %s %s pre=%d post=%d seed=%d ==' % (
        args.which, args.mode, args.pre, args.post, args.seed_offset))
    print('n', len(out), 'wall', wall,
          'ok', sum(r['ok'] for r in out),
          'cert', sum(r['certified'] for r in out),
          'partial_fail', sum(r['partial_fail'] for r in out),
          'probes', sum(r['probes'] for r in out),
          'search_lp', sum(r['search_lp'] for r in out),
          'cert_lp', sum(r['cert_lp'] for r in out),
          'pin_lp', sum(r['pin_lp'] for r in out),
          'total_lp', sum(r['total_lp'] for r in out),
          'round_work', sum(r['round_work'] for r in out),
          't', round(sum(r['t'] for r in out), 2))
    print('probe hist', dict(sorted(collections.Counter(
        r['probes'] for r in out).items())))
    print('zero-probe', sum(r['probes'] == 0 for r in out),
          'one-probe', sum(r['probes'] == 1 for r in out),
          'two-plus', sum(r['probes'] >= 2 for r in out))
    print('out', args.out)


if __name__ == '__main__':
    main()
