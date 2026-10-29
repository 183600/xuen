"""AEGIS-PACT benchmark: synthesized branching + static shield on gap cases.

Usage:
  .venv/bin/python exp/v10c/bench_aegis.py --quick
  .venv/bin/python exp/v10c/bench_aegis.py
"""
import json
import sys
import time
import argparse

sys.path[:0] = ['exp/v10c', 'exp/v10b', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from aegis import (SEARCH_FEATURES, eval_policy, summarize, load_gap_cases,
                   policy_from_vector, StaticAnalyzer, root_box)
from pso import PSO


TRAIN_SOURCES = {1, 3, 9, 10, 13}


def vec(**kw):
    x = [0.0] * len(SEARCH_FEATURES) + [0.5]
    for k, v in kw.items():
        if k == 'split':
            x[-1] = float(v)
        else:
            x[SEARCH_FEATURES.index(k)] = float(v)
    return x


HAND = {
    'default': None,
    'p': vec(p=1.0),
    'entropy': vec(entropy=1.0),
    'spread': vec(spread=1.0),
    'p+ent': vec(p=1.0, entropy=1.0),
    'p+spr': vec(p=1.0, spread=1.0),
    'p+ent+spr': vec(p=1.0, entropy=1.0, spread=1.0),
    'spr+ent': vec(spread=1.0, entropy=1.0),
}


def split_cases(cases):
    train = [d for d in cases if d['src'] in TRAIN_SOURCES]
    holdout = [d for d in cases if d['src'] not in TRAIN_SOURCES]
    return train, holdout


def pso_subset(train, k=0):
    # Four hard training cases: enough signal, bounded PSO cost.
    want = {'orig-01', 'orig-03', 'orig-09', 'orig-10', 'orig-13'}
    sub = [d for d in train if d['case'] in want]
    if k:
        pert = sorted([d for d in train if d['kind'] == 'pert'],
                      key=lambda d: d.get('nodes0', 0), reverse=True)[:k]
        sub += pert
    return sub


def static_report(cases):
    out = []
    for d in cases:
        h = int(d['opt']) - 1
        lo, hi = root_box(d['inst'], h)
        sa = StaticAnalyzer(d['inst'])
        p = sa.close(h, lo, hi)
        out.append(dict(case=d['case'], kind=d['kind'], src=d['src'],
                        h=h, hit=bool(p is not None),
                        cert=(p.cert.get('kind') if p else None)))
    return dict(n=len(out), hits=sum(r['hit'] for r in out), rows=out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--quick', action='store_true')
    ap.add_argument('--particles', type=int, default=4)
    ap.add_argument('--iters', type=int, default=4)
    ap.add_argument('--cap', type=int, default=200)
    ap.add_argument('--timelimit', type=float, default=1.0)
    args = ap.parse_args()
    if args.quick:
        args.particles, args.iters = 4, 2
        args.cap, args.timelimit = 250, 1.5

    cases = load_gap_cases()
    train, holdout = split_cases(cases)
    subset = pso_subset(train, 0)
    print('cases', len(cases), 'train', len(train), 'holdout', len(holdout),
          'pso_subset', [d['case'] for d in subset], flush=True)

    stat = static_report(cases)
    print('static root closure hits', stat['hits'], '/', stat['n'],
          flush=True)

    bounds = [(-3.0, 3.0)] * len(SEARCH_FEATURES) + [(0.15, 0.85)]
    seeds = [vec(spread=1.0), vec(p=1.0, spread=1.0),
             vec(spread=1.0, entropy=1.0),
             vec(p=1.0, entropy=1.0, spread=1.0)]

    def fit(x):
        rows = eval_policy(x, subset, cap=args.cap,
                           timelimit=args.timelimit, fallback=False,
                           use_static=True)
        s = summarize(rows)
        return (s['total_lp'] + 2000 * (s['n'] - s['ok']))

    t0 = time.time()
    pso = PSO(len(bounds), bounds, n_particles=args.particles,
              iters=args.iters, seed=7)
    res = pso.run(fit, seeds=seeds)
    print('pso best fit', round(res['fit'], 2), 'evals', res['evals'],
          'cache', res['cache'], 't_eval', res['t_eval'],
          'wall', round(time.time() - t0, 1), flush=True)
    print('pso x', [round(v, 4) for v in res['x']], flush=True)

    # Compare the synthesized policy with two hand baselines and the
    # default.  Selection is by PSO fitness on the training subset; the
    # holdout is never used to choose theta.
    best_name = 'pso'
    best_x = res['x']
    cand = [('default', None), ('spread', vec(spread=1.0)),
            ('spr+ent', vec(spread=1.0, entropy=1.0)),
            ('pso', best_x)]
    print('selected', best_name, flush=True)

    eval_rows = {}
    for name, x in cand:
        tr = eval_policy(x, train, cap=700, timelimit=8.0,
                         fallback=True, use_static=True)
        ho = eval_policy(x, holdout, cap=700, timelimit=8.0,
                         fallback=True, use_static=True)
        eval_rows[name] = dict(train=summarize(tr), holdout=summarize(ho),
                               train_rows=tr, holdout_rows=ho,
                               theta=x)
        print('eval', name, '| train', eval_rows[name]['train'],
              '| holdout', eval_rows[name]['holdout'], flush=True)

    out = dict(
        config=vars(args),
        train_sources=sorted(TRAIN_SOURCES),
        train_cases=[d['case'] for d in train],
        holdout_cases=[d['case'] for d in holdout],
        pso_subset=[d['case'] for d in subset],
        static=stat,
        pso=dict(x=res['x'], fit=res['fit'], evals=res['evals'],
                 cache=res['cache'], t_eval=res['t_eval'],
                 history=res['history']),
        selected=best_name,
        selected_x=best_x,
        eval=eval_rows,
        wall=round(time.time() - t0, 2),
    )
    with open('exp/v10c/bench_aegis.json', 'w') as f:
        json.dump(out, f, indent=1)
    print('saved exp/v10c/bench_aegis.json wall', out['wall'], flush=True)


if __name__ == '__main__':
    main()
