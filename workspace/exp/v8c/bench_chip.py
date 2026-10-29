"""v8.1 CRISP benchmark: base 141 + perturbations 60 + stress 51.

Runs three rows per instance:
  * cab  : v9.0 CAB baseline (loaded from exp/v9d/bench_opt.json)
  * bound: CRISP bounds + CAB oracle
  * crisp: CRISP bounds + CHD oracle
"""
import sys
import json
import time

sys.path[:0] = ['exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a',
                'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60',
                'exp/v13']

from chip import (CRISP, CRISPBounds, base_corpus, pert_corpus,
                  stress_corpus, run, corpus_rows)


def load_baseline():
    try:
        return json.load(open('exp/v9d/bench_opt.json'))
    except Exception:
        return None


def main():
    baseline = load_baseline()
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
            row = dict(name=name, idx=idx, known=known)
            if baseline is not None:
                blist = baseline.get(tag, [])
                b = blist[ci] if ci < len(blist) else None
                if b is not None:
                    row['cab'] = dict(
                        q=b.get('q'), lp=b.get('lp'), yn=b.get('yn'),
                        mc=b.get('mc'), t=b.get('t'),
                        opt=b.get('opt'), certified=b.get('certified'),
                        audit=b.get('audit'), proof=b.get('proof'),
                        cert_h=b.get('cert_h'))
            for meth, cls in [('bound', CRISPBounds), ('crisp', CRISP)]:
                r = run(cls, inst, known, name, idx)
                row[meth] = dict(
                    q=r['queries'], lp=r['lp'], yn=r['yes_nodes'],
                    mc=r['mc_evals'], t=r['t'], opt=r['opt'],
                    certified=r['certified'], audit=r['audit'],
                    proof=r['proof'], cert_h=r['cert_h'],
                    lifts=r.get('lifts'), drops=r.get('drops'),
                    cert_bad=r.get('cert_bad'), unknown=r.get('unknown'),
                    ok=r['ok'])
            out[tag].append(row)
            if ci % 25 == 0:
                print(tag, ci, flush=True)
        print(tag, 'time', round(time.time() - t0, 2), flush=True)
    json.dump(out, open('exp/v8c/bench_chip.json', 'w'), indent=1)
    for tag in ['base', 'pert', 'stress']:
        print('\n==', tag)
        for meth in ['cab', 'bound', 'crisp']:
            rows = [r[meth] for r in out[tag] if meth in r]
            if not rows:
                continue
            print(meth, dict(n=len(rows),
                             cert=sum(bool(x['certified']) for x in rows),
                             q=sum(x['q'] or 0 for x in rows),
                             lp=sum(x['lp'] or 0 for x in rows),
                             yn=sum(x['yn'] or 0 for x in rows),
                             mc=sum(x['mc'] or 0 for x in rows),
                             t=round(sum(x['t'] or 0 for x in rows), 2)))
    print('\n== total')
    for meth in ['cab', 'bound', 'crisp']:
        rows = [r[meth] for tag in out for r in out[tag] if meth in r]
        print(meth, dict(n=len(rows),
                         cert=sum(bool(x['certified']) for x in rows),
                         q=sum(x['q'] or 0 for x in rows),
                         lp=sum(x['lp'] or 0 for x in rows),
                         yn=sum(x['yn'] or 0 for x in rows),
                         mc=sum(x['mc'] or 0 for x in rows),
                         t=round(sum(x['t'] or 0 for x in rows), 2)))


if __name__ == '__main__':
    main()
