"""v8.2 HSC ablation: cut pool x canonical state table on the 252 corpus.

Four deterministic variants are interleaved on the same corpus so that
machine load is shared:
  crisp : v8.1 CRISP + CHD (random fallback on)
  cut   : CRISP + shared lazy-cut pool (CHD)
  tt    : CRISP + canonical LDS, no random fallback (HSC)
  both  : HSC + shared cut pool
"""
import sys
import json
import time

sys.path[:0] = ['exp/v8d', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from chip import (base_corpus, pert_corpus, stress_corpus, CRISP, run)
from pool_crisp import PoolCRISP
from hsc_crisp import HSCRISP
from hsc_pool import HSCPool

VARIANTS = [('crisp', CRISP), ('cut', PoolCRISP),
            ('tt', HSCRISP), ('both', HSCPool)]


def main():
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
            row = dict(name=name, idx=idx, known=known)
            for vname, cls in VARIANTS:
                r = run(cls, inst, known, name, idx)
                row[vname] = dict(q=r['queries'], lp=r['lp'],
                                  yn=r['yes_nodes'], t=r['t'],
                                  ok=r['ok'],
                                  certified=r['certified'],
                                  unknown=r['unknown'])
            out[tag].append(row)
            if ci % 25 == 0:
                print(tag, ci, flush=True)
        print(tag, 'time', round(time.time() - t0, 2), flush=True)
    json.dump(out, open('exp/v8d/bench_ablate.json', 'w'), indent=1)
    print('\n== total')
    for tag in ['base', 'pert', 'stress', 'all']:
        rows = ([r for r in out[tag]] if tag != 'all'
                else [r for t in out for r in out[t]])
        for vname, _ in VARIANTS:
            print(tag, vname,
                  dict(q=sum(r[vname]['q'] for r in rows),
                       lp=sum(r[vname]['lp'] for r in rows),
                       yn=sum(r[vname]['yn'] for r in rows),
                       t=round(sum(r[vname]['t'] for r in rows), 3),
                       cert=sum(bool(r[vname]['certified']) for r in rows),
                       ok=sum(bool(r[vname]['ok']) for r in rows)))


if __name__ == '__main__':
    main()
