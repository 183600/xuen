"""Benchmark DBR-ICF on the main 252 and weak 160 corpora.

Usage (from the workspace root):
    .venv/bin/python exp/v8u/bench_dbr.py --which weak --k 4 --batches 1
    .venv/bin/python exp/v8u/bench_dbr.py --which both --k 4 --batches 3
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

from dbr import run_dbr
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
    keys = ('probes', 'search_lp', 'cert_lp', 'pin_lp', 'beam_work',
            'beam_hits', 'beam_tight', 'beam_batches', 'base_hits',
            'reinsert_hits', 'probe_no', 'probe_yes', 'probe_unknown',
            'partial_ok', 'partial_fail')
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
    ap.add_argument('--k', type=int, default=4)
    ap.add_argument('--batches', type=int, default=1)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    whiches = ('main', 'weak') if args.which == 'both' else (args.which,)
    out = {}
    for which in whiches:
        rows = list(rows_for(which))
        t0 = time.time()
        rs = []
        for j, (c, name, idx, inst, known, init) in enumerate(rows):
            r = run_dbr(inst, known, name, idx, initial=init,
                        k=args.k, max_batches=args.batches)
            r['corpus'] = c
            rs.append(r)
            if j % 50 == 0:
                print('  ..', which, j, '/', len(rows),
                      't', round(time.time() - t0, 1), flush=True)
        out[which] = rs
        s = summarize(rs)
        print('\n==', which, 'k', args.k, 'batches', args.batches, '==')
        print(json.dumps(s, sort_keys=True))
        print('wall', round(time.time() - t0, 2))
    path = args.out
    if path is None:
        path = 'exp/v8u/bench_dbr_%s_k%d_b%d.json' % (
            args.which, args.k, args.batches)
    with open(path, 'w') as f:
        json.dump(out, f, indent=1)
    print('wrote', path)


if __name__ == '__main__':
    main()
