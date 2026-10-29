"""Benchmark TDC-PACT on the strong 252 and weak 160 suites."""
from __future__ import annotations

import argparse
import collections
import json
import sys
import time

sys.path[:0] = ['exp/v9x', 'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8u',
                'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f', 'exp/v8e',
                'exp/v8g', 'exp/v8c', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from icf import corpora
from hap import weak_rows
from tdc import run_tdc_icf


MODES = ('off', 'pso', 'beam', 'tdc')


def suite_rows(suite):
    if suite == 'strong':
        return [(c, n, i, inst, known, None)
                for c, n, i, inst, known in corpora()]
    rows = []
    for c, n, i, inst, known, init in weak_rows(4):
        rows.append((c, n, i, inst, known, init))
    return rows


def summarize(rows, tag):
    out = dict(
        tag=tag, n=len(rows),
        ok=sum(bool(r['ok']) for r in rows),
        certified=sum(bool(r['certified']) for r in rows),
        partial_fail=sum(r['partial_fail'] for r in rows),
        partial_ok=sum(r['partial_ok'] for r in rows),
        q=sum(r['queries'] for r in rows),
        lp=sum(r['pact_lp'] for r in rows),
        cert_lp=sum(r['pact_cert_lp'] for r in rows),
        pin_lp=sum(r['pin_lp'] for r in rows),
        total_lp=sum(r['pact_lp'] + r['pact_cert_lp'] + r['pin_lp']
                     for r in rows),
        tdc_calls=sum(r['tdc_calls'] for r in rows),
        tdc_success=sum(r['tdc_success'] for r in rows),
        tdc_nodes=sum(r['tdc_nodes'] for r in rows),
        tdc_rollouts=sum(r['tdc_rollouts'] for r in rows),
        trie_admitted=sum(r['trie_admitted'] for r in rows),
        trie_merged=sum(r['trie_merged'] for r in rows),
        pso_evals=sum(r['pso_evals'] for r in rows),
        pso_t=round(sum(r['pso_t'] for r in rows), 3),
        tdc_t=round(sum(r['tdc_t'] for r in rows), 3),
        t=round(sum(r['t'] for r in rows), 3),
    )
    print(tag, json.dumps(out, sort_keys=True), flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--suite', choices=('strong', 'weak'), default='strong')
    ap.add_argument('--modes', default=','.join(MODES))
    ap.add_argument('--width', type=int, default=20)
    ap.add_argument('--nodecap', type=int, default=5000)
    ap.add_argument('--timelimit', type=float, default=0.02)
    ap.add_argument('--npart', type=int, default=8)
    ap.add_argument('--iters', type=int, default=12)
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--stall', type=int, default=4)
    ap.add_argument('--max-gap', type=int, default=99)
    ap.add_argument('--policy', default='lower-first')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--out', default='')
    args = ap.parse_args()

    rows = suite_rows(args.suite)
    if args.limit:
        rows = rows[:args.limit]
    modes = [x for x in args.modes.split(',') if x]
    out = dict(config=vars(args), summaries={}, rows={})
    for mode in modes:
        t0 = time.time()
        recs = []
        for corpus, name, idx, inst, known, init in rows:
            r = run_tdc_icf(
                inst, known, name, idx, policy=args.policy,
                initial=init, use_pact_init=(args.suite == 'strong'),
                use_tdc=(mode != 'off'), mode=mode,
                width=(0 if mode == 'pso' else args.width),
                nodecap=args.nodecap, timelimit=args.timelimit,
                n_particles=args.npart, iters=args.iters,
                seed=args.seed, stall=args.stall,
                tdc_max_gap=args.max_gap,
            )
            r['corpus'] = corpus
            recs.append(r)
        wall = round(time.time() - t0, 2)
        tag = '%s/%s/w%d/tl%s' % (args.suite, mode, args.width,
                                  args.timelimit)
        s = summarize(recs, tag)
        s['wall'] = wall
        out['summaries'][mode] = s
        out['rows'][mode] = recs
        print('wall', wall, flush=True)
    if args.out:
        with open(args.out, 'w') as f:
            json.dump(out, f, indent=1)
        print('saved', args.out)


if __name__ == '__main__':
    main()
