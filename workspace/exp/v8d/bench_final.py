"""v8.3 final benchmark: HSC + cut pool + narrow-bracket UB-1 probe.

Baseline: exp/v8c/bench_chip.json (v8.1 CRISP + CHD).
"""
import sys
import json
import time

sys.path[:0] = ['exp/v8d', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from chip import (base_corpus, pert_corpus, stress_corpus,
                  corpus_rows)
from hybrid_crisp import HybridCRISP


def run_final(inst, known, name, idx):
    t0 = time.time()
    co = HybridCRISP(inst)
    r = co.optimize()
    dt = time.time() - t0
    r.update(name=name, idx=idx, known=known, t=round(dt, 4))
    r['cut_pool'] = len(getattr(co, 'cut_pool', ()))
    b = getattr(co, 'chip', None) or {}
    r['chip_lb'] = b.get('lb')
    r['chip_ub'] = b.get('ub')
    r['lifts'] = b.get('lifts')
    r['drops'] = b.get('drops')
    r['cert_bad'] = b.get('cert_bad')
    r['ok'] = bool(r['certified'] and r['opt'] == known
                   and r['audit'] and r['proof']
                   and r['cert_h'] == known - 1)
    return r


def main():
    old = json.load(open('exp/v8c/bench_chip.json'))
    out = {'base': [], 'pert': [], 'stress': []}
    for tag, corpus in [('base', base_corpus()),
                        ('pert', pert_corpus()),
                        ('stress', stress_corpus())]:
        t0 = time.time()
        for ci, rec in enumerate(corpus):
            if tag in ('base', 'pert'):
                name, idx, inst, known = rec
            else:
                idx, known, inst = rec
                name = 'stress'
            r = run_final(inst, known, name, idx)
            b = old[tag][ci]['crisp']
            r['old'] = dict(q=b['q'], lp=b['lp'], yn=b['yn'], t=b['t'])
            out[tag].append(r)
            if ci % 25 == 0:
                print(tag, ci, flush=True)
        print(tag, 'time', round(time.time() - t0, 2), flush=True)
    json.dump(out, open('exp/v8d/bench_final.json', 'w'), indent=1)
    print('\n== final')
    for tag in ['base', 'pert', 'stress', 'all']:
        rows = ([r for r in out[tag]] if tag != 'all'
                else [r for t in out for r in out[t]])
        agg = dict(n=len(rows),
                   cert=sum(bool(r['certified']) for r in rows),
                   ok=sum(bool(r['ok']) for r in rows),
                   q=sum(r['queries'] for r in rows),
                   lp=sum(r['lp'] for r in rows),
                   yn=sum(r['yes_nodes'] for r in rows),
                   t=round(sum(r['t'] for r in rows), 3),
                   pool=sum(r['cut_pool'] for r in rows))
        oldagg = dict(q=sum(r['old']['q'] for r in rows),
                      lp=sum(r['old']['lp'] for r in rows),
                      yn=sum(r['old']['yn'] for r in rows),
                      t=round(sum(r['old']['t'] for r in rows), 3))
        print(tag, 'new', agg)
        print(tag, 'old', oldagg)


if __name__ == '__main__':
    main()
