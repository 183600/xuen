"""Benchmark EBA-ICF on the main 252 and weak 160 corpora."""
import argparse
import collections
import json
import os
import sys
import time

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from eba import run_eba
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
            'eba_work', 'round_hits', 'eba_hits', 'lds_hits', 'ea_hits',
            'route_hits', 'partial_ok', 'partial_fail')
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
    ap.add_argument('--which', choices=['main', 'weak'], default='weak')
    ap.add_argument('--mode', default='lds',
                    choices=['lds', 'full'])
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--lds-nodes', type=int, default=1500)
    ap.add_argument('--lds-time', type=float, default=0.02)
    ap.add_argument('--ea-time', type=float, default=0.03)
    ap.add_argument('--seed-base', type=int, default=0)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()
    rows = list(rows_for(args.which))
    if args.limit:
        rows = rows[:args.limit]
    out = []
    t0 = time.time()
    for k, (c, name, idx, inst, known, init) in enumerate(rows):
        r = run_eba(inst, known, name, idx, initial=init,
                    seed=k + args.seed_base, lds_nodes=args.lds_nodes,
                    lds_time=args.lds_time, ea_time=args.ea_time,
                    do_ea=(args.mode == 'full'),
                    do_route=(args.mode == 'full'))
        r['corpus'] = c
        out.append(r)
        if k % 25 == 0:
            print(' ..', args.which, args.mode, k, '/', len(rows),
                  't', round(time.time() - t0, 1), flush=True)
    s = summarize(out)
    print(json.dumps(s, sort_keys=True))
    print('wall', round(time.time() - t0, 2))
    path = args.out
    if path is None:
        path = 'exp/v8u/bench_eba_%s_%s.json' % (args.which, args.mode)
    with open(path, 'w') as f:
        json.dump(out, f, indent=1)
    print('wrote', path)


if __name__ == '__main__':
    main()
