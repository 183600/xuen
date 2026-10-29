"""v8.4 LBP-ALC benchmark: LP-bound pinning + residual gap scan.

Baseline rows are loaded from exp/v8c/bench_chip.json (deterministic
CRISP+CHD).  New rows use exp/v8e/lbp.py.
"""
import sys
import json
import time

sys.path[:0] = ['exp/v8e', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from lbp import LBP, LBPNoEnergy, run
from chip import base_corpus, pert_corpus, stress_corpus


CORPORA = [('base', base_corpus()), ('pert', pert_corpus()),
           ('stress', stress_corpus())]


def aggregate(rows):
    return dict(
        n=len(rows),
        cert=sum(bool(r['certified']) for r in rows),
        ok=sum(bool(r['ok']) for r in rows),
        q=sum(r['queries'] for r in rows),
        lp=sum(r['lp'] for r in rows),
        pin_lp=sum((r.get('pin_lp') or 0) for r in rows),
        cert_lp=sum((r.get('cert_lp') or 0) for r in rows),
        lp_primal=sum((r.get('lp_primal') or 0) for r in rows),
        cert_cp=sum((r.get('cert_cp') or 0) for r in rows),
        cert_fb=sum((r.get('cert_fb') or 0) for r in rows),
        cert_full=sum((r.get('cert_full') or 0) for r in rows),
        yn=sum(r['yes_nodes'] for r in rows),
        mc=sum(r['mc_evals'] for r in rows),
        t=round(sum(r['t'] for r in rows), 3),
        qzero=sum(1 for r in rows if r['queries'] == 0),
        qone=sum(1 for r in rows if r['queries'] == 1),
        qgt1=sum(1 for r in rows if r['queries'] > 1),
        hardq=sum(1 for r in rows for x in r['trace']
                  if (x.get('yes_nodes') or 0) > 0),
        gaps={k: sum(1 for r in rows if r.get('gap_opt') == k)
              for k in range(-1, 6)},
        span={k: sum(1 for r in rows if r.get('gap_lp') == k)
              for k in range(0, 8)},
        bad=sum((r.get('lp_bound_bad') or 0) for r in rows),
    )


def main():
    old = json.load(open('exp/v8c/bench_chip.json'))
    out = {'base': [], 'pert': [], 'stress': []}
    for tag, corpus in CORPORA:
        t0 = time.time()
        for ci, rec in enumerate(corpus):
            if tag in ('base', 'pert'):
                name, idx, inst, known = rec
            else:
                idx, known, inst = rec
                name = 'stress'
            r = run(LBP, inst, known, name, idx)
            b = old[tag][ci]['crisp']
            r['old'] = dict(q=b['q'], lp=b['lp'], yn=b['yn'], t=b['t'])
            out[tag].append(r)
            if ci % 25 == 0:
                print(tag, ci, 'pin', r['pin_lb'], 'gap', r['gap_opt'],
                      'q', r['queries'], 'lp', r['lp'],
                      'yn', r['yes_nodes'], 'ok', r['ok'], flush=True)
        print(tag, 'time', round(time.time() - t0, 2), flush=True)
    json.dump(out, open('exp/v8e/bench_lbp.json', 'w'), indent=1)

    print('\n== aggregate')
    for tag in ['base', 'pert', 'stress', 'all']:
        rows = ([r for r in out[tag]] if tag != 'all'
                else [r for t in out for r in out[t]])
        new = aggregate(rows)
        oldagg = dict(
            q=sum(r['old']['q'] for r in rows),
            lp=sum(r['old']['lp'] for r in rows),
            yn=sum(r['old']['yn'] for r in rows),
            t=round(sum(r['old']['t'] for r in rows), 3),
        )
        print(tag, 'new', new)
        print(tag, 'old', oldagg)

    # no-energy ablation
    print('\n== no-energy ablation')
    ab = {'base': [], 'pert': [], 'stress': []}
    for tag, corpus in CORPORA:
        t0 = time.time()
        for ci, rec in enumerate(corpus):
            if tag in ('base', 'pert'):
                name, idx, inst, known = rec
            else:
                idx, known, inst = rec
                name = 'stress'
            ab[tag].append(run(LBPNoEnergy, inst, known, name, idx))
        print(tag, 'time', round(time.time() - t0, 2), flush=True)
    json.dump(ab, open('exp/v8e/bench_lbp_noenergy.json', 'w'), indent=1)
    for tag in ['base', 'pert', 'stress', 'all']:
        rows = ([r for r in ab[tag]] if tag != 'all'
                else [r for t in ab for r in ab[t]])
        print(tag, 'ab', aggregate(rows))


if __name__ == '__main__':
    main()
