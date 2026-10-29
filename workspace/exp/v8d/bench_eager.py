"""v8.2 EAGER-ALC benchmark and ablation on base 141 + pert 60 + stress 51."""
import sys
import json
import time

sys.path[:0] = ['exp/v8d', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from chip import (base_corpus, pert_corpus, stress_corpus)
from eager import EAGER


VARIANTS = [
    ('orders_promote', dict(ea_budget=0, promote=True, probe_budget=0)),
    ('random256', dict(ea_budget=256, ea_mode='random',
                       promote=True, probe_budget=0)),
    ('ea128', dict(ea_budget=128, promote=True, probe_budget=0)),
    ('ea256', dict(ea_budget=256, promote=True, probe_budget=0)),
    ('ea512', dict(ea_budget=512, promote=True, probe_budget=0)),
    ('ea512_p1', dict(ea_budget=512, ea_patience=1,
                      promote=True, probe_budget=0)),
    ('ea512_b32p1', dict(ea_budget=512, ea_block=32,
                         ea_patience=1, promote=True, probe_budget=0)),
    ('ea256_nopromote', dict(ea_budget=256, promote=False,
                             probe_budget=0)),
    ('ea256_probe2', dict(ea_budget=256, promote=True, probe_budget=2)),
]


def load_crisp():
    try:
        d = json.load(open('exp/v8c/bench_chip.json'))
        return {tag: d[tag] for tag in ('base', 'pert', 'stress')}
    except Exception:
        return None


def corpus(tag):
    return {'base': base_corpus(), 'pert': pert_corpus(),
            'stress': stress_corpus()}[tag]


def main():
    crisp = load_crisp()
    out = {name: {'base': [], 'pert': [], 'stress': []}
           for name, _ in VARIANTS}
    for tag in ['base', 'pert', 'stress']:
        for pos, rec in enumerate(corpus(tag)):
            if tag == 'stress':
                idx, known, inst = rec
                name = 'stress'
            else:
                name, idx, inst, known = rec
            for vname, kw in VARIANTS:
                t0 = time.time()
                co = EAGER(inst, **kw)
                r = co.optimize()
                dt = time.time() - t0
                row = dict(name=name, idx=idx, pos=pos, known=known,
                           opt=r['opt'], lb=r['lb'],
                           certified=r['certified'], q=r['queries'],
                           free=r['free_queries'], lp=r['lp'],
                           yn=r['yes_nodes'], mc=r['mc_evals'],
                           t=round(dt, 4), audit=r['audit'],
                           proof=r['proof'], cert_h=r['cert_h'],
                           probes=r.get('probes'),
                           bisect=r.get('bisect'),
                           ea_evals=r.get('ea_evals'),
                           ea_improved=r.get('ea_improved'),
                           prep=r.get('prep'))
                row['ok'] = bool(row['certified']
                                 and row['opt'] == known
                                 and row['audit'] and row['proof']
                                 and row['cert_h'] == known - 1)
                out[vname][tag].append(row)
            if pos % 40 == 0:
                print(tag, pos, flush=True)
        print(tag, 'done', flush=True)
    json.dump(out, open('exp/v8d/bench_eager.json', 'w'), indent=1)
    print('\n%-18s %4s %4s %5s %6s %6s %6s %6s %8s' %
          ('variant', 'n', 'cert', 'ok', 'q', 'free', 'lp', 'yn', 't'))
    for vname, _ in VARIANTS:
        rows = [r for tag in out[vname] for r in out[vname][tag]]
        print('%-18s %4d %4d %5d %6d %6d %6d %6d %8.2f' %
              (vname, len(rows),
               sum(r['certified'] for r in rows),
               sum(r['ok'] for r in rows),
               sum(r['q'] for r in rows),
               sum(r['free'] for r in rows),
               sum(r['lp'] for r in rows),
               sum(r['yn'] for r in rows),
               sum(r['t'] for r in rows)))
    if crisp is not None:
        rows = [r for tag in crisp for r in crisp[tag]]
        print('%-18s %4d %4d %5d %6d %6d %6d %6d %8.2f' %
              ('crisp(reference)', len(rows),
               sum(bool(r['crisp']['certified']) for r in rows),
               0, sum(r['crisp']['q'] or 0 for r in rows),
               0, sum(r['crisp']['lp'] or 0 for r in rows),
               sum(r['crisp']['yn'] or 0 for r in rows),
               sum(r['crisp']['t'] or 0 for r in rows)))


if __name__ == '__main__':
    main()
