"""SPARC benchmark: primal swarm + certified bracket contraction."""
import argparse
import collections
import json
import sys
import time

sys.path[:0] = ['exp/v91', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from icf import corpora
from sparc import run_sparc


CONFIGS = [
    ('weak_pso0_binary', dict(init='weak', pso_on=False, policy='binary')),
    ('weak_pso0_lower', dict(init='weak', pso_on=False, policy='lower-first')),
    ('weak_pso0_inc1', dict(init='weak', pso_on=False, policy='incumbent-1')),
    ('weak_pso0_inc3', dict(init='weak', pso_on=False, policy='incumbent-3')),
    ('weak_pso0_pact', dict(init='weak', pso_on=False, policy='pact')),
    ('weak_pso1_binary', dict(init='weak', pso_on=True, policy='binary')),
    ('weak_pso1_lower', dict(init='weak', pso_on=True, policy='lower-first')),
    ('weak_pso1_inc1', dict(init='weak', pso_on=True, policy='incumbent-1')),
    ('weak_pso1_inc3', dict(init='weak', pso_on=True, policy='incumbent-3')),
    ('weak_pso1_adapt', dict(init='weak', pso_on=True, policy='adaptive')),
    ('weak_pso1_adaptgap', dict(init='weak', pso_on=True, policy='adaptive-gap')),
    ('weak_pso1_adaptinit', dict(init='weak', pso_on=True, policy='adaptive-init')),
    ('strong_pso0_lower', dict(init='strong', pso_on=False, policy='lower-first')),
    ('strong_pso0_inc1', dict(init='strong', pso_on=False, policy='incumbent-1')),
    ('strong_pso1_inc1', dict(init='strong', pso_on=True, policy='incumbent-1')),
    ('strong_pso1_lower', dict(init='strong', pso_on=True, policy='lower-first')),
    ('strong_pso1_adaptgap', dict(init='strong', pso_on=True, policy='adaptive-gap')),
    ('strong_pso1_adaptinit', dict(init='strong', pso_on=True, policy='adaptive-init')),
]


def summarize(rows):
    out = dict(
        n=len(rows),
        ok=sum(bool(r.get('ok')) for r in rows),
        certified=sum(bool(r.get('certified')) for r in rows),
        partial_fail=sum(r.get('partial_fail', 0) for r in rows),
        partial_ok=sum(r.get('partial_ok', 0) for r in rows),
        q=sum(r.get('queries', 0) for r in rows),
        lp=sum(r.get('pact_lp', 0) for r in rows),
        cert=sum(r.get('pact_cert_lp', 0) for r in rows),
        pin=sum(r.get('pin_lp', 0) for r in rows),
        total_lp=sum(r.get('total_lp', 0) for r in rows),
        pso_evals=sum(r.get('pso_evals', 0) for r in rows),
        pso_time=round(sum(r.get('pso_time', 0.0) for r in rows), 3),
        t=round(sum(r.get('t', 0.0) for r in rows), 3),
        gap0=sum(r.get('ub0', 0) - r.get('lb0', 0) for r in rows),
        gap_pso=sum(r.get('ub_pso', 0) - r.get('lb0', 0) for r in rows),
        gap_final=sum(r.get('ub', 0) - r.get('lb', 0) for r in rows),
    )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--only', default='')
    ap.add_argument('--out', default='exp/v91/bench_sparc.json')
    ap.add_argument('--npart', type=int, default=8)
    ap.add_argument('--iters', type=int, default=12)
    ap.add_argument('--seed', type=int, default=7)
    args = ap.parse_args()

    rows_all = list(corpora())
    if args.limit:
        rows_all = rows_all[:args.limit]
    only = set(x for x in args.only.split(',') if x)
    configs = [c for c in CONFIGS if not only or c[0] in only]
    out = dict(config={k: v for k, v in vars(args).items()},
               n_instances=len(rows_all),
               configs={}, rows={})
    for tag, kw in configs:
        t0 = time.time()
        rows = []
        for corpus, name, idx, inst, known in rows_all:
            r = run_sparc(inst, known, name, idx,
                          n_particles=args.npart, iters=args.iters,
                          seed=args.seed, **kw)
            r['corpus'] = corpus
            rows.append(r)
        wall = round(time.time() - t0, 2)
        out['configs'][tag] = summarize(rows)
        out['configs'][tag]['wall'] = wall
        out['rows'][tag] = rows
        s = out['configs'][tag]
        print('==', tag, 'wall', wall, 'ok', s['ok'], 'cert', s['certified'],
              'q', s['q'], 'lp', s['lp'], 'certLP', s['cert'],
              'pin', s['pin'], 'totalLP', s['total_lp'],
              'psoEval', s['pso_evals'], 'psoT', s['pso_time'],
              'gap0', s['gap0'], 'gapPSO', s['gap_pso'],
              'auditFail', s['partial_fail'], flush=True)
    with open(args.out, 'w') as f:
        json.dump(out, f, indent=1)
    print('saved', args.out)


if __name__ == '__main__':
    main()
