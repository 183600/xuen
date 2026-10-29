"""Benchmark WIPCF on the main 252 and weak 160 corpora."""
import argparse
import collections
import json
import os
import sys
import time

sys.path[:0] = ['exp/v94', 'exp/v93', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from wipcf import run_wipcf
from icf import corpora
from hap import weak_rows


def rows_for(which):
    if which == 'weak':
        for c, name, idx, inst, known, init in weak_rows(4):
            yield c, name, idx, inst, known, init
    elif which == 'main':
        for c, name, idx, inst, known in corpora():
            yield c, name, idx, inst, known, None
    else:
        raise ValueError(which)


def summarize(rows):
    keys = ('probes', 'search_lp', 'cert_lp', 'pin_lp', 'round_work',
            'round_hits', 'cfa_hits', 'dom_hits', 'prescan_no',
            'prescan_open', 'prescan_fail', 'prescan_work',
            'partial_ok', 'partial_fail')
    z = {k: sum((r.get(k, 0) or 0) for r in rows) for k in keys}
    z['n'] = len(rows)
    z['ok'] = sum(bool(r.get('ok')) for r in rows)
    z['certified'] = sum(bool(r.get('certified')) for r in rows)
    z['partial_checks'] = z['partial_ok'] + z['partial_fail']
    z['probe_hist'] = dict(sorted(collections.Counter(
        r.get('probes', 0) for r in rows).items()))
    z['prescan_time'] = round(sum((r.get('prescan_time', 0) or 0)
                                  for r in rows), 2)
    z['t'] = round(sum((r.get('t', 0) or 0) for r in rows), 2)
    return z


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--which', choices=['main', 'weak', 'both'],
                    default='weak')
    ap.add_argument('--mode', default='pd')
    ap.add_argument('--prescan', action='store_true', default=True)
    ap.add_argument('--no-prescan', dest='prescan', action='store_false')
    ap.add_argument('--prescan-index', action=argparse.BooleanOptionalAction,
                    default=True)
    ap.add_argument('--prescan-iters', type=int, default=8)
    ap.add_argument('--prescan-checks', type=int, default=None)
    ap.add_argument('--prescan-gap', type=int, default=64)
    ap.add_argument('--dom-decode', action=argparse.BooleanOptionalAction,
                    default=False)
    ap.add_argument('--restarts', type=int, default=50)
    ap.add_argument('--time-cap', type=float, default=0.08)
    ap.add_argument('--no-cfa', action='store_true')
    ap.add_argument('--seed-base', type=int, default=0)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    whiches = ('main', 'weak') if args.which == 'both' else (args.which,)
    out = {}
    for which in whiches:
        rows = list(rows_for(which))
        rs = []
        t0 = time.time()
        for k, (c, name, idx, inst, known, init) in enumerate(rows):
            r = run_wipcf(inst, known, name, idx, initial=init,
                          mode=args.mode, use_cfa=not args.no_cfa,
                          restarts=args.restarts, time_cap=args.time_cap,
                          seed=k + args.seed_base, prescan=args.prescan,
                          prescan_index=args.prescan_index,
                          prescan_iters=args.prescan_iters,
                          prescan_checks=args.prescan_checks,
                          prescan_gap=args.prescan_gap,
                          dom_decode=args.dom_decode)
            r['corpus'] = c
            rs.append(r)
            if k % 50 == 0:
                print('  ..', which, k, '/', len(rows),
                      't', round(time.time() - t0, 1), flush=True)
        out[which] = rs
        s = summarize(rs)
        print('\n==', which, '==')
        print(json.dumps(s, sort_keys=True))
        print('wall', round(time.time() - t0, 2))
    path = args.out
    if path is None:
        path = 'exp/v94/bench_wipcf_%s%s%s.json' % (
            args.which, '' if args.prescan else '_noprescan',
            '_idx' if args.prescan_index else '')
    with open(path, 'w') as f:
        json.dump(out, f, indent=1)
    print('wrote', path)


if __name__ == '__main__':
    main()
