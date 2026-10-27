"""Benchmark AXIOM-ICF: synthesized plans + live frontier.

Usage (from workspace root):
  .venv/bin/python exp/v8u/bench_axiom.py --suite weak --policy plan
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'exp' / d) for d in (
    'v8u', 'v8o', 'v8i', 'v8h', 'v8f', 'v8e', 'v8g', 'v8c',
    'v9d', 'v9c', 'v9b', 'v8a', 'v76', 'v72', 'v71', 'v61',
    'v60', 'v13')]

from axiom import (run_axiom, ConstantCost, RobustCost)
from hap import weak_rows
from icf import corpora


def rows_for(suite):
    if suite == 'main':
        for c, n, i, inst, known in corpora():
            yield c, n, i, inst, known, None
    else:
        for c, n, i, inst, known, init in weak_rows(4):
            yield c, n, i, inst, known, init


def cost_for(name):
    if name == 'unit':
        return ConstantCost(1.0, 1.0, 'unit')
    if name == 'c15':
        return ConstantCost(1.0, 5.0, 'c15')
    if name == 'c55':
        return ConstantCost(1.5, 5.0, 'c55')
    if name == 'c25':
        return ConstantCost(2.0, 5.0, 'c25')
    if name == 'c35':
        return ConstantCost(3.34, 5.71, 'c35')
    if name == 'c13':
        return ConstantCost(1.0, 3.0, 'c13')
    if name == 'robust':
        return RobustCost([ConstantCost(1.0, 1.0, 'unit'),
                           ConstantCost(1.0, 3.0, 'c13'),
                           ConstantCost(1.0, 5.0, 'c15'),
                           ConstantCost(2.0, 5.0, 'c25')], 'robust')
    raise ValueError(name)


def summarize(rows):
    keys = ('probes', 'pact_lp', 'pact_cert_lp', 'split_lp', 'nodes',
            'splits', 'leaves', 'unknown', 'partial_ok', 'partial_fail')
    z = {k: sum(r.get(k, 0) for r in rows) for k in keys}
    z['n'] = len(rows)
    z['certified'] = sum(bool(r.get('certified')) for r in rows)
    z['ok'] = sum(bool(r.get('ok')) for r in rows)
    z['plan_audit'] = sum(bool(r.get('plan_audit')) for r in rows)
    z['t'] = round(sum(r.get('t', 0.0) for r in rows), 2)
    return z


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--suite', choices=('main', 'weak'), default='weak')
    ap.add_argument('--policy', default='plan')
    ap.add_argument('--cost', default='c15')
    ap.add_argument('--nodecap', type=int, default=0)
    ap.add_argument('--max-probes', type=int, default=128)
    ap.add_argument('--max-leaves', type=int, default=64)
    ap.add_argument('--out', default='')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--no-split', action='store_true')
    args = ap.parse_args()

    rows = []
    t0 = time.time()
    todo = list(rows_for(args.suite))
    if args.limit:
        todo = todo[:args.limit]
    for k, (c, name, idx, inst, known, init) in enumerate(todo):
        cost = cost_for(args.cost) if args.policy == 'plan' else None
        r = run_axiom(inst, known, name, idx, initial=init,
                      policy=args.policy, cost=cost,
                      nodecap=(args.nodecap or None),
                      max_probes=args.max_probes,
                      max_leaves=args.max_leaves,
                      allow_split=not args.no_split)
        r['corpus'] = c
        rows.append(r)
        if (k + 1) % 20 == 0:
            print(' ', k + 1, '/', len(todo), 'wall',
                  round(time.time() - t0, 1), flush=True)
    tag = '%s_%s' % (args.suite, args.policy)
    if args.policy == 'plan':
        tag += '_' + args.cost
    if args.nodecap:
        tag += '_b%d' % args.nodecap
    if args.no_split:
        tag += '_nosplit'
    out = args.out or str(ROOT / 'exp' / 'v8u' /
                          ('bench_axiom_%s.json' % tag))
    with open(out, 'w') as f:
        json.dump(rows, f, indent=1)
    print(tag, json.dumps(summarize(rows), sort_keys=True))
    print('wrote', out)


if __name__ == '__main__':
    main()
