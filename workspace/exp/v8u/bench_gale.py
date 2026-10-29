"""Benchmark GALE-PACT: global floor, frontier lift, lazy ledger, BSP batch.

Examples (from the workspace root):

    .venv/bin/python exp/v8u/bench_gale.py --suite normal
    .venv/bin/python exp/v8u/bench_gale.py --suite weak
    .venv/bin/python exp/v8u/bench_gale.py --suite weak --scout-batch 2 --workers 4
    .venv/bin/python exp/v8u/bench_gale.py --suite weak --no-scout
    .venv/bin/python exp/v8u/bench_gale.py --suite weak --limit 20 --out /tmp/gale20.json
"""
import argparse
import json
import multiprocessing as mp
import sys
import time

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from icf import corpora
from hap import weak_rows
from gale import run_gale


def items(which, limit):
    if which == 'normal':
        out = [(c, name, idx, inst, known, None)
               for c, name, idx, inst, known in corpora()]
    else:
        out = [(c, name, idx, inst, known, ini)
               for c, name, idx, inst, known, ini in weak_rows(4)]
    return out[:limit] if limit else out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--suite', choices=['normal', 'weak'], default='normal')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--scout-batch', type=int, default=1)
    ap.add_argument('--workers', type=int, default=0,
                    help='0 = serial; >0 = process pool size')
    ap.add_argument('--no-scout', action='store_true')
    ap.add_argument('--scout-gap', type=int, default=5)
    ap.add_argument('--scout-cap', type=int, default=8)
    ap.add_argument('--b0', type=int, default=1)
    ap.add_argument('--bmax', type=int, default=8)
    ap.add_argument('--out', default='')
    args = ap.parse_args()

    pool = None
    if args.workers > 0 and args.scout_batch > 1:
        pool = mp.get_context('fork').Pool(args.workers)
    rows = []
    t0 = time.time()
    try:
        for c, name, idx, inst, known, ini in items(args.suite, args.limit):
            r = run_gale(inst, known, name, idx, initial=ini,
                         scout=not args.no_scout,
                         scout_gap=args.scout_gap,
                         scout_cap=args.scout_cap,
                         B0=args.b0, Bmax=args.bmax,
                         policy='lower',
                         scout_batch=args.scout_batch, pool=pool)
            r['corpus'] = c
            rows.append(r)
    finally:
        if pool is not None:
            pool.close()
            pool.join()
    dt = time.time() - t0

    def sm(k):
        return sum((r.get(k, 0) or 0) for r in rows)

    print('suite', args.suite, 'n', len(rows),
          'ok', sum(1 for r in rows if r.get('ok')),
          'probes', sm('probes'), 'scouts', sm('scouts'),
          'splits', sm('splits'), 'lifts', sm('lifts'),
          'lp', sm('lp'), 't', round(dt, 2),
          'max_leaves', max((r.get('max_leaves', 0) or 0) for r in rows)
          if rows else 0,
          'partial_fail', sm('partial_fail'))
    if args.out:
        with open(args.out, 'w') as f:
            json.dump({'rows': rows, 'total_s': dt}, f, default=str)
        print('wrote', args.out)


if __name__ == '__main__':
    main()
