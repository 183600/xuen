#!/usr/bin/env python3
"""Negative-control benchmark for HAP-ICF (hash-consed iterative deepening).

Run from the workspace root:
    .venv/bin/python exp/v8u/bench_hap.py --suite probe --mode hybrid:4
    .venv/bin/python exp/v8u/bench_hap.py --suite weak --mode full
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

from hap import HapMemo, decide_hat, run_hap, weak_rows
from icf import corpora


def probe_rows():
    scan = json.load(open(ROOT / 'exp' / 'v8u' / 'depth_scan.json'))
    key = {(r['corpus'], r['name'], r['idx']): r for r in scan}
    return [(c, n, i, inst, known, key[(c, n, i)]['L'])
            for c, n, i, inst, known in corpora()
            if (c, n, i) in key]


def summarize(rows):
    outer = any('pact_lp' in r for r in rows)
    return dict(
        n=len(rows),
        probes=sum(r.get('probes', 1) for r in rows),
        lp=sum(r.get('pact_lp', r.get('lp_solves', 0)) for r in rows),
        cert=sum(r.get('pact_cert_lp', r.get('cert_lp', 0)) for r in rows),
        memo=sum(r.get('memo_hits', 0) for r in rows),
        lp_hits=sum(r.get('lp_hits', 0) for r in rows),
        no=sum(r.get('verdict') is False for r in rows),
        yes=sum(r.get('verdict') is True for r in rows),
        unknown=(sum(r.get('unknown', 0) for r in rows) if outer else
                 sum(r.get('verdict') is None for r in rows)),
        certified=sum(bool(r.get('certified')) for r in rows),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--suite', choices=('probe', 'main', 'weak'),
                    default='probe')
    ap.add_argument('--mode', default='hybrid:4')
    ap.add_argument('--policy', default='gap:1')
    args = ap.parse_args()
    t0 = time.time()
    out = []
    if args.suite == 'probe':
        for c, name, idx, inst, known, h in probe_rows():
            memo = HapMemo(inst)
            r, levels = decide_hat(inst, h, memo, mode=args.mode)
            r['corpus'] = c
            r['levels_count'] = len(levels)
            out.append(r)
    elif args.suite == 'main':
        for c, name, idx, inst, known in corpora():
            r = run_hap(inst, known, name, idx, mode=args.mode,
                        oracle='hap')
            r['corpus'] = c
            out.append(r)
    else:
        for c, name, idx, inst, known, initial in weak_rows(4):
            r = run_hap(inst, known, name, idx, policy=args.policy,
                        mode=args.mode, oracle='hap', initial=initial)
            r['corpus'] = c
            out.append(r)
    s = summarize(out)
    s['wall'] = round(time.time() - t0, 2)
    s['suite'] = args.suite
    s['mode'] = args.mode
    print(json.dumps(s, sort_keys=True))
    dst = ROOT / 'exp' / 'v8u' / ('bench_hap_%s_%s.json' %
                                 (args.suite, args.mode.replace(':', '')))
    def clean(r):
        return {k: v for k, v in r.items()
                if k not in ('proof', 'levels', 'steps')}
    with open(dst, 'w') as f:
        json.dump([clean(r) for r in out], f)
    print('wrote', dst)


if __name__ == '__main__':
    main()
