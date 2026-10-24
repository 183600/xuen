"""v10.0 LION benchmark: CRISP vs CRISP+LP-guided descent (LION)."""
import sys
import json
import time

sys.path[:0] = ['exp/v10a', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from chip import CRISP, base_corpus, pert_corpus, stress_corpus
from lion import LION


def run(cls, inst, known, **kw):
    t0 = time.time()
    co = cls(inst, **kw)
    r = co.optimize()
    dt = time.time() - t0
    out = dict(q=r['queries'], lp=r['lp'], yn=r['yes_nodes'],
               mc=r['mc_evals'], t=dt, opt=r['opt'],
               certified=r['certified'], audit=r['audit'],
               proof=r['proof'], cert_h=r['cert_h'],
               lb0=r.get('lb0'), ub0=r.get('ub0'),
               ok=bool(r['certified'] and r['opt'] == known
                       and r['audit'] and r['proof']
                       and r['cert_h'] == known - 1))
    b = getattr(co, 'chip', None) or {}
    out.update(chip_lb=b.get('lb'), chip_ub=b.get('ub'),
               lifts=b.get('lifts'), drops=b.get('drops'),
               cert_bad=b.get('cert_bad'))
    d = getattr(co, 'descent', None) or {}
    out.update(desc_lb=d.get('lb'), desc_ub=d.get('ub'),
               desc_lp=d.get('lp'), desc_nodes=d.get('nodes'),
               desc_steps=d.get('steps'), desc_drops=d.get('drops'),
               desc_closes=d.get('closes'), desc_time=d.get('lp_time', 0)
               + d.get('lds_time', 0))
    return out


def agg(rows):
    keys = ['q', 'lp', 'yn', 'mc', 't', 'desc_lp', 'desc_nodes',
            'desc_time', 'lifts', 'drops', 'desc_drops', 'desc_closes']
    out = dict(n=len(rows), cert=sum(r['certified'] for r in rows),
               ok=sum(r['ok'] for r in rows))
    for k in keys:
        out[k] = round(sum((r.get(k) or 0) for r in rows), 4)
    out['exact'] = sum(r['chip_lb'] == r['chip_ub'] for r in rows)
    out['desc_exact'] = sum(r['desc_lb'] == r['desc_ub'] for r in rows)
    return out


def main():
    out = {}
    for tag, corpus in [('base', base_corpus()),
                        ('pert', pert_corpus()),
                        ('stress', stress_corpus())]:
        rows = []
        t0 = time.time()
        for ci, rec in enumerate(corpus):
            if tag == 'stress':
                idx, known, inst = rec
                name = 'stress'
            else:
                name, idx, inst, known = rec
            row = dict(name=name, idx=idx, known=known)
            row['crisp'] = run(CRISP, inst, known)
            row['lion'] = run(LION, inst, known)
            rows.append(row)
            if ci % 25 == 0:
                print(tag, ci, flush=True)
        out[tag] = rows
        print(tag, 'time', round(time.time() - t0, 2), flush=True)
    json.dump(out, open('exp/v10a/bench_lion.json', 'w'), indent=1)
    for tag in ['base', 'pert', 'stress']:
        print('\n==', tag)
        rows = out[tag]
        for meth in ['crisp', 'lion']:
            print(meth, agg([r[meth] for r in rows]))
    print('\n== total')
    for meth in ['crisp', 'lion']:
        print(meth, agg([r[meth] for tag in out for r in out[tag]]))


if __name__ == '__main__':
    main()
