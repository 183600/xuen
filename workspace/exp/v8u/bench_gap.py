#!/usr/bin/env python3
"""Benchmark GAP-ICF: lower-first for small gaps, bisection for wide gaps.

Usage (from the workspace root):
    .venv/bin/python exp/v8u/bench_gap.py --tau 5
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

from hap import weak_rows
from icf import corpora, run_icf


def run_suite(rows, tau, with_initial):
    out = []
    for row in rows:
        if with_initial:
            c, name, idx, inst, known, initial = row
        else:
            c, name, idx, inst, known = row
            initial = None
        r = run_icf(inst, known, name, idx, policy='gap:%d' % tau,
                    initial=initial)
        r['corpus'] = c
        out.append(r)
    return out


def summarize(rows):
    keys = ('probes', 'pact_lp', 'pact_cert_lp', 'pin_lp')
    z = {k: sum(r.get(k, 0) for r in rows) for k in keys}
    z['certified'] = sum(bool(r['certified']) for r in rows)
    z['ok'] = sum(bool(r['ok']) for r in rows)
    z['unknown'] = sum(r.get('unknown', 0) for r in rows)
    z['partial_fail'] = sum(r.get('partial_fail', 0) for r in rows)
    z['total_lp'] = z['pact_lp'] + z['pact_cert_lp'] + z['pin_lp']
    z['n'] = len(rows)
    return z


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tau', type=int, default=5)
    ap.add_argument('--out', default='')
    args = ap.parse_args()
    t0 = time.time()
    main_rows = run_suite(list(corpora()), args.tau, False)
    weak = run_suite(weak_rows(4), args.tau, True)
    print('GAP-ICF tau=%d  wall=%.2fs' % (args.tau, time.time() - t0))
    for tag, rows in (('main-252', main_rows), ('weak-160', weak)):
        s = summarize(rows)
        print(tag, json.dumps(s, sort_keys=True))
    out = args.out or str(ROOT / 'exp' / 'v8u' /
                          ('bench_gap_tau%d.json' % args.tau))
    with open(out, 'w') as f:
        json.dump(dict(tau=args.tau, main=main_rows, weak=weak), f)
    print('wrote', out)


if __name__ == '__main__':
    main()
