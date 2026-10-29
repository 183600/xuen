"""v8.2 HSC benchmark: CRISP+CHD (v8.1) vs CRISP+HSC (v8.2) on 252 cases."""
import sys
import json
import time

sys.path[:0] = ['exp/v8d', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from chip import (base_corpus, pert_corpus, stress_corpus, run,
                  corpus_rows)
from hsc_crisp import HSCRISP


def main():
    old = json.load(open('exp/v8c/bench_chip.json'))
    out = {'base': [], 'pert': [], 'stress': []}
    for tag, corpus in [('base', base_corpus()),
                        ('pert', pert_corpus()),
                        ('stress', stress_corpus())]:
        t0 = time.time()
        for ci, rec in enumerate(corpus):
            if tag == 'base':
                name, idx, inst, known = rec
            elif tag == 'pert':
                name, idx, inst, known = rec
            else:
                idx, known, inst = rec
                name = 'stress'
            r = run(HSCRISP, inst, known, name, idx)
            row = dict(name=name, idx=idx, known=known,
                       q=r['queries'], lp=r['lp'], yn=r['yes_nodes'],
                       mc=r['mc_evals'], t=r['t'], opt=r['opt'],
                       certified=r['certified'], audit=r['audit'],
                       proof=r['proof'], cert_h=r['cert_h'],
                       lifts=r.get('lifts'), drops=r.get('drops'),
                       cert_bad=r.get('cert_bad'),
                       unknown=r.get('unknown'), ok=r['ok'],
                       lb=r['lb'], lb0=r['lb0'], ub0=r['ub0'],
                       trace=r['trace'])
            base = old[tag][ci]
            row['old'] = dict(q=base['crisp']['q'], lp=base['crisp']['lp'],
                              yn=base['crisp']['yn'],
                              t=base['crisp']['t'])
            out[tag].append(row)
            if ci % 25 == 0:
                print(tag, ci, flush=True)
        print(tag, 'time', round(time.time() - t0, 2), flush=True)
    json.dump(out, open('exp/v8d/bench_hsc.json', 'w'), indent=1)

    print('\n== total')
    for tag in ['base', 'pert', 'stress', 'all']:
        rows = ([r for r in out[tag]] if tag != 'all'
                else [r for t in out for r in out[t]])
        agg = dict(n=len(rows),
                   cert=sum(bool(r['certified']) for r in rows),
                   ok=sum(bool(r['ok']) for r in rows),
                   q=sum(r['q'] for r in rows),
                   lp=sum(r['lp'] for r in rows),
                   yn=sum(r['yn'] for r in rows),
                   t=round(sum(r['t'] for r in rows), 3))
        old = dict(q=sum(r['old']['q'] for r in rows),
                   lp=sum(r['old']['lp'] for r in rows),
                   yn=sum(r['old']['yn'] for r in rows),
                   t=round(sum(r['old']['t'] for r in rows), 3))
        print(tag, 'HSC', agg, 'old', old)


if __name__ == '__main__':
    main()
