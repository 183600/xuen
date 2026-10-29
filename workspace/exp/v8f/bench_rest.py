"""v8.5 REST-ALC benchmark: CRISP vs CRISP+REST on the 252 corpus."""
import sys
import json
import time
import argparse

sys.path[:0] = ['exp/v8f', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from rest import run_rest
from chip import base_corpus, pert_corpus, stress_corpus


def agg(rows):
    return dict(
        n=len(rows),
        cert=sum(bool(r['certified']) for r in rows),
        ok=sum(bool(r['ok']) for r in rows),
        q=sum(r['queries'] for r in rows),
        lp=sum(r['lp'] for r in rows),
        yn=sum(r['yes_nodes'] for r in rows),
        mc=sum(r['mc_evals'] for r in rows),
        t=round(sum(r['t'] for r in rows), 3),
        rest_lifts=sum(r['rest_lifts'] for r in rows),
        rest_checks=sum(r['rest_checks'] for r in rows),
        rest_unk=sum(r['rest_unk'] for r in rows),
        rest_t=round(sum(r['rest_t'] for r in rows), 3),
        q0=sum(1 for r in rows if r['queries'] == 0),
        q1=sum(1 for r in rows if r['queries'] == 1),
        qgt=sum(1 for r in rows if r['queries'] > 1),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--K', type=int, default=12)
    ap.add_argument('--budget', type=int, default=60)
    ap.add_argument('--tlim', type=float, default=0.4)
    ap.add_argument('--early', type=int, default=0)
    ap.add_argument('--seed', type=int, default=4040)
    ap.add_argument('--only', default='')
    ap.add_argument('--out', default='')
    args = ap.parse_args()
    tag_filter = set(x for x in args.only.split(',') if x)
    out = {}
    for tag, corpus in [('base', base_corpus()),
                        ('pert', pert_corpus()),
                        ('stress', stress_corpus())]:
        if tag_filter and tag not in tag_filter:
            continue
        t0 = time.time()
        rows = []
        for ci, rec in enumerate(corpus):
            if tag in ('base', 'pert'):
                name, idx, inst, known = rec
            else:
                idx, known, inst = rec
                name = 'stress'
            r = run_rest(inst, known, name, idx, K=args.K,
                         budget=args.budget, tlim=args.tlim,
                         seed=args.seed, early_stop=args.early)
            rows.append(r)
            if ci % 10 == 0:
                print(tag, ci, r['queries'], r['rest_lifts'],
                      round(r['t'], 2), flush=True)
        out[tag] = rows
        print(tag, 'time', round(time.time() - t0, 2),
              json.dumps(agg(rows)), flush=True)
    if args.out:
        json.dump(out, open(args.out, 'w'), indent=1)
    print('\n== total')
    allrows = [r for tag in out for r in out[tag]]
    print(json.dumps(agg(allrows), indent=1))


if __name__ == '__main__':
    main()
