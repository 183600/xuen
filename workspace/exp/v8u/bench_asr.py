"""Benchmark ASR-ICF on the main 252 and weak 160 corpora.

Usage (from the workspace root):
    .venv/bin/python exp/v8u/bench_asr.py --which weak --mode asr
    .venv/bin/python exp/v8u/bench_asr.py --which both --mode both
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

from asr import run_asr
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
            'round_hits', 'cfa_hits', 'reinsert_work', 'reinsert_hits',
            'reinsert_tight', 'partial_ok', 'partial_fail')
    z = {k: sum((r.get(k, 0) or 0) for r in rows) for k in keys}
    z['n'] = len(rows)
    z['ok'] = sum(bool(r.get('ok')) for r in rows)
    z['certified'] = sum(bool(r.get('certified')) for r in rows)
    z['partial_checks'] = z['partial_ok'] + z['partial_fail']
    z['probe_hist'] = dict(sorted(collections.Counter(
        r.get('probes', 0) for r in rows).items()))
    z['defect_hist'] = dict(sorted(collections.Counter(
        r.get('defect', 0) for r in rows).items()))
    z['t'] = round(sum((r.get('t', 0) or 0) for r in rows), 2)
    return z


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--which', choices=['main', 'weak', 'both'],
                    default='both')
    ap.add_argument('--mode', default='asr')
    ap.add_argument('--restarts', type=int, default=50)
    ap.add_argument('--time-cap', type=float, default=0.08)
    ap.add_argument('--seed-base', type=int, default=0)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    modes = ('pd', 'asr') if args.mode == 'both' else (args.mode,)
    whiches = ('main', 'weak') if args.which == 'both' else (args.which,)
    out = {}
    for which in whiches:
        rows = list(rows_for(which))
        out[which] = {}
        for mode in modes:
            t0 = time.time()
            rs = []
            for k, (c, name, idx, inst, known, init) in enumerate(rows):
                r = run_asr(inst, known, name, idx, initial=init,
                            mode=mode, restarts=args.restarts,
                            time_cap=args.time_cap,
                            seed=k + args.seed_base)
                r['corpus'] = c
                rs.append(r)
                if k % 50 == 0:
                    print('  ..', which, mode, k, '/', len(rows),
                          't', round(time.time() - t0, 1), flush=True)
            out[which][mode] = rs
            s = summarize(rs)
            print('\n==', which, mode, '==')
            print(json.dumps(s, sort_keys=True))
            print('wall', round(time.time() - t0, 2))
    path = args.out
    if path is None:
        path = 'exp/v8u/bench_asr_%s_%s.json' % (args.which, args.mode)
    with open(path, 'w') as f:
        json.dump(out, f, indent=1)
    print('wrote', path)


if __name__ == '__main__':
    main()
